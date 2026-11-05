/**
 * Who listens (owner's request 2026-10-23): the login page asks once per device - a login is kept by the server,
 * a guest's choice in the browser - and a guest's state stays in this browser.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { begin, canRemoveSongs, continueAsGuest, guest, initials, logIn, me, session } from '../src/player/account'
import { api, keepStateInBrowser } from '../src/player/api'

const anna = { id: 'a1b2c3d4e5f6', name: 'Anna Lee', admin: false, avatar: false, color: '#4fbf7f' }
const admin = { id: 'admin', name: 'Admin', admin: true, avatar: false, color: '#e4573d' }

function answer(body: unknown, status = 200): Response {
  return { ok: status < 400, status, url: '', json: async () => body } as unknown as Response
}

describe('account', () => {
  beforeEach(() => {
    localStorage.clear()
    guest.value = false
    me.value = null
    keepStateInBrowser(false)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('asks on a new device, and not again once somebody logged in', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => answer({ login: true, user: admin, chosen: false, local: true, users: [anna], admin })))
    expect(await begin()).toBe(false)
    vi.stubGlobal('fetch', vi.fn(async () => answer({ login: true, user: anna, chosen: true, local: false, users: [anna] })))
    expect(await begin()).toBe(true)
    expect(me.value?.name).toBe('Anna Lee')
    // a player without the login (older, or a shared one): as before
    vi.stubGlobal('fetch', vi.fn(async () => answer({ login: false, user: null, chosen: true, local: true, users: [] })))
    expect(await begin()).toBe(true)
  })

  it('remembers a guest, who keeps the state in this browser', async () => {
    continueAsGuest()
    expect(guest.value).toBe(true)
    const state = { playlists: [], favorites: ['x'], plays: {}, last_played: {}, tags: {}, settings: {} }
    await api.saveState(state)
    expect((await api.state()).favorites).toEqual(['x'])
    vi.stubGlobal('fetch', vi.fn(async () => answer({ login: true, user: null, chosen: false, local: false, users: [] })))
    expect(await begin()).toBe(true) // the choice is remembered
  })

  it('logs in and says why not', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => answer({ error: 'The name or the password is not right.' }, 401)))
    await expect(logIn(anna.id, 'nope')).rejects.toThrow('not right')
    vi.stubGlobal('fetch', vi.fn(async () => answer({ user: anna })))
    await logIn(anna.id, 'secret')
    expect(me.value?.id).toBe(anna.id)
    expect(initials('Anna Lee')).toBe('AL')
    expect(initials('bo')).toBe('BO')
  })

  it('offers removing songs to whom the server lets remove them', () => {
    session.value = { login: true, user: anna, chosen: true, local: false, users: [anna] }
    me.value = anna // a listener or a maker
    expect(canRemoveSongs.value).toBe(false)
    me.value = { ...anna, helper: true } // the admins' group
    expect(canRemoveSongs.value).toBe(true)
    me.value = null // a guest
    expect(canRemoveSongs.value).toBe(false)
    me.value = admin
    expect(canRemoveSongs.value).toBe(true)
    // a player without the login: its server lets every page remove, as before
    session.value = { login: false, user: null, chosen: true, local: true, users: [] }
    me.value = null
    expect(canRemoveSongs.value).toBe(true)
    session.value = null
  })
})
