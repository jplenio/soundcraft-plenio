/** The visuals' settings (owner's request 2026-10-30): a visual's name shows it at once - with *Fixed* it stays - and
 * the lists of one visual show the Nova visuals not offered here, greyed with why. */
import { afterEach, describe, expect, it } from 'vitest'
import { type App, createApp, h, nextTick } from 'vue'

import VisualsPanel from '../src/player/components/VisualsPanel.vue'
import { settings } from '../src/player/store'
import { keepTiming, novaTimings, setGpuSupport } from '../src/player/visuals/gpu'
import { NOVA } from '../src/player/visuals/nova'

const GPU = { webgl: true, float: true, why: '', card: 'Test card' }
// the one that plays, one too heavy here, one not working in this browser, one being timed, one more that plays smoothly
const [playing, heavy, broken, waiting, other] = NOVA

let app: App | null = null
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
  setGpuSupport(null)
  novaTimings.value = {}
  settings.visuals.mode = 'auto'
})

async function panel(mode: 'fixed' | 'random') {
  setGpuSupport(GPU)
  for (const def of NOVA) keepTiming(def.id, 1)
  keepTiming(heavy.id, 1000)
  keepTiming(broken.id, -1)
  const timings = { ...novaTimings.value }
  delete timings[waiting.id]
  novaTimings.value = timings
  settings.visuals.mode = mode
  const played: string[] = []
  const host = document.createElement('div')
  document.body.append(host)
  app = createApp({ render: () => h(VisualsPanel, { active: playing.id, onPlay: (id: string) => played.push(id) }) })
  app.mount(host)
  await nextTick()
  return { host, played }
}

async function clickName(host: HTMLElement, name: string): Promise<void> {
  const button = [...host.querySelectorAll<HTMLButtonElement>('.pick .name')].find((b) => b.textContent?.trim() === name)
  expect(button, name).toBeTruthy()
  button!.click()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('the visuals’ settings', () => {
  it('list the Nova visuals not offered here with Fixed, greyed with why', async () => {
    const { host } = await panel('fixed')
    const fixed = [...host.querySelectorAll('select')].find((s) => [...s.options].some((o) => o.value === playing.id && o.textContent?.trim() === playing.name))
    expect(fixed).toBeTruthy()
    const option = (id: string) => [...fixed!.options].find((o) => o.value === id)
    expect(option(playing.id)?.disabled).toBe(false)
    expect(option(other.id)?.disabled).toBe(false)
    expect(option(heavy.id)?.disabled).toBe(true)
    expect(option(heavy.id)?.textContent).toContain('too heavy for this graphics card')
    expect(option(broken.id)?.textContent).toContain('not working in this browser')
    expect(option(waiting.id)?.textContent).toContain('being timed')
  })

  it('show a visual at once when its name is clicked, and keep it with Fixed', async () => {
    const { host, played } = await panel('fixed')
    await clickName(host, other.name)
    expect(settings.visuals.fixed).toBe(other.id)
    expect(played).toEqual([other.id])
  })

  it('show it until the next change in the other modes', async () => {
    const { host, played } = await panel('random')
    const before = settings.visuals.fixed
    await clickName(host, other.name)
    expect(settings.visuals.fixed).toBe(before)
    expect(played).toEqual([other.id])
    // a visual not offered here has no name to click
    expect([...host.querySelectorAll('.pick .name')].map((b) => b.textContent?.trim())).not.toContain(heavy.name)
  })
})
