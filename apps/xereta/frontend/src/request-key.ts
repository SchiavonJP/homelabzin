/** A request identifier, never an authentication token. Web Crypto works on HTTP too. */
export function requestKey(
  prefix: 'web' | 'retry',
  source: Partial<Pick<Crypto, 'getRandomValues'>> = globalThis.crypto,
): string {
  if (!source || typeof source.getRandomValues !== 'function') {
    throw new Error('Não foi possível iniciar com segurança. Atualize o navegador e tente novamente.')
  }
  const bytes = new Uint8Array(16)
  source.getRandomValues(bytes)
  return prefix + ':' + Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
}
