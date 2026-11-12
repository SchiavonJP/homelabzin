import { describe, expect, test } from 'bun:test'
import { requestKey } from '../../src/request-key'

describe('request identifiers without secure-context-only APIs', () => {
  const httpCrypto = { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) }
  test('manual and retry keys work when randomUUID is absent', () => {
    expect('randomUUID' in httpCrypto).toBe(false)
    expect(requestKey('web', httpCrypto)).toMatch(/^web:[a-f0-9]{32}$/)
    expect(requestKey('retry', httpCrypto)).toMatch(/^retry:[a-f0-9]{32}$/)
    expect(requestKey('web', httpCrypto)).not.toBe(requestKey('web', httpCrypto))
  })
  test('missing secure randomness fails with a useful message', () => {
    expect(() => requestKey('web', {})).toThrow('Atualize o navegador')
  })
})
