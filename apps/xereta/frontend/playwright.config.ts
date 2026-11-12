import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  use: {
    baseURL: 'http://xereta-http.test:4173',
    headless: true,
    launchOptions: {
      ...(process.env.XERETA_CHROME_PATH ? { executablePath: process.env.XERETA_CHROME_PATH } : {}),
      args: ['--host-resolver-rules=MAP xereta-http.test 127.0.0.1', '--no-proxy-server'],
    },
  },
  webServer: {
    command: 'python3 -m http.server 4173 --bind 127.0.0.1 --directory dist',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
  },
})
