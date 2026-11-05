// The API prompts ComfyUI's own frontend makes of the Song API's templates - the references the Song API's
// converter (plenio/core/workflow_prompt.py) is tested against (tests/fixtures/song_api/).
//
// For each template with `extra.plenio_api` and each variant below: load it like the template browser does,
// change what the variant says with the frontend's own widgets and modes, and save `app.graphToPrompt()`'s
// prompt and workflow as `<template id>.<variant>.json`.
//
// Needs a running ComfyUI with Plenio (tools/dev_server.py; no models needed). Usage:
//
//   node tools/frontend_prompts.mjs --url http://127.0.0.1:8190 [--channel msedge] [--out tests/fixtures/song_api]
//
// Playwright: `playwright-core` with a system browser (PLAYWRIGHT_MODULE points at it).

import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const PROJECT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, value, index, all) => {
    if (value.startsWith('--')) pairs.push([value.slice(2), all[index + 1]?.startsWith('--') ? true : all[index + 1] ?? true])
    return pairs
  }, []),
)
const URL = args.url ?? 'http://127.0.0.1:8190'
const OUT = path.resolve(args.out ?? path.join(PROJECT, 'tests', 'fixtures', 'song_api'))
fs.mkdirSync(OUT, { recursive: true })

function loadPlaywright() {
  const require = createRequire(import.meta.url)
  for (const name of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean)) {
    try {
      return require(name)
    } catch {}
  }
  throw new Error('Playwright not found: npm install -g playwright-core (or set PLAYWRIGHT_MODULE)')
}

// What each variant changes: widgets by node type (a DynamicCombo's new choice first), modes by node title.
// The Song API's tests make the same changes through the API's fields and compare the prompts.
const VARIANTS = {
  'yue2-song': {
    shipped: {},
    instrumental: {
      widgets: [
        ['PlenioSongBrief', 'vocals', 'instrumental'],
        ['PlenioSongBrief', 'vocals.lead_instrument', 'saxophone'],
        ['PlenioSongBrief', 'genre', 'smooth jazz'],
        ['PlenioHQMastering', 'hq_mastering', true],
      ],
      modes: [[['Cover Art', 'Cover seed', 'Cover preview'], 4]],
    },
  },
  'yue2-cover': {
    shipped: { widgets: [['LoadAudio', 'audio', 'plenio-api-0123456789ab-source.mp3']] },
    excerpt: {
      widgets: [
        ['LoadAudio', 'audio', 'plenio-api-0123456789ab-source.mp3'],
        ['TrimAudioDuration', 'start_index', 30],
        ['PlenioCoverBrief', 'vocals', 'new lyrics'],
        ['PlenioCoverBrief', 'vocals.theme', 'a summer night'],
      ],
      modes: [[['Excerpt (optional)'], 0]],
    },
  },
}

const { chromium } = loadPlaywright()
const browser = await chromium.launch({ ...(args.channel ? { channel: args.channel } : {}) })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
await page.goto(URL, { waitUntil: 'networkidle' })
await page.waitForFunction(() => window.app && window.app.graph, null, { timeout: 90000 })
await page.keyboard.press('Escape')

const templates = fs
  .readdirSync(path.join(PROJECT, 'example_workflows'))
  .filter((f) => f.endsWith('.json'))
  .map((f) => [f.slice(0, -5), JSON.parse(fs.readFileSync(path.join(PROJECT, 'example_workflows', f), 'utf8'))])
  .filter(([, data]) => data.extra?.plenio_api?.id)

for (const [name, template] of templates) {
  const id = template.extra.plenio_api.id
  for (const [variant, change] of Object.entries(VARIANTS[id] ?? { shipped: {} })) {
    await page.evaluate(async ([w, n]) => { await window.app.loadGraphData(w, true, true, n) }, [template, name])
    await page.waitForTimeout(1200)
    await page.keyboard.press('Escape')
    const result = await page.evaluate(async ([widgets, modes]) => {
      const graph = window.app.graph
      const missing = []
      for (const [type, name, value] of widgets ?? []) {
        const node = graph.nodes.find((x) => x.type === type)
        const widget = node?.widgets?.find((w) => w.name === name)
        if (!widget) {
          missing.push(`${type}.${name}`)
          continue
        }
        if (widget.options?.values && !widget.options.values.includes(value)) widget.options.values.push(value)
        widget.value = value
        widget.callback?.(value)
        // a DynamicCombo makes its new widgets after the change
        await new Promise((resolve) => setTimeout(resolve, 150))
      }
      for (const [titles, mode] of modes ?? []) for (const node of graph.nodes) if (titles.includes(node.title)) node.mode = mode
      const { output, workflow } = await window.app.graphToPrompt()
      return { output, workflow, missing }
    }, [change.widgets, change.modes])
    if (result.missing.length) throw new Error(`${id} ${variant}: no widget ${result.missing.join(', ')}`)
    // the notes' texts left out (the converter skips notes), one line of JSON
    for (const graph of [result.workflow, ...(result.workflow.definitions?.subgraphs ?? [])])
      for (const node of graph.nodes ?? []) if (node.type === 'MarkdownNote' || node.type === 'Note') node.widgets_values = ['']
    const file = path.join(OUT, `${id}.${variant}.json`)
    fs.writeFileSync(file, JSON.stringify({ template: name, variant, change, prompt: result.output, workflow: result.workflow }) + '\n')
    console.log(`wrote ${path.relative(PROJECT, file)} (${Object.keys(result.output).length} nodes)`)
  }
}
await browser.close()
