import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
    testDir: "./tests/e2e",
    timeout: 60_000,
    expect: { timeout: 15_000 },
    fullyParallel: false,
    retries: 1,
    workers: 1,
    reporter: [["list"]],

    use: {
        baseURL: "http://localhost:3001",
        trace: "on-first-retry",
        headless: true,
    },

    projects: [
        {
            name: "chromium",
            use: { ...devices["Desktop Chrome"] },
        },
    ],
});
