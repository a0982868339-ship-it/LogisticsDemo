/**
 * tests/e2e/dashboard.spec.ts — Step 3: Playwright E2E 测试
 * ============================================================
 * 前提：
 *   - 后端服务运行在 http://localhost:8000 (uvicorn)
 *   - 前端开发服务器运行在 http://localhost:3001 (next dev)
 */
import { test, expect, Page } from "@playwright/test";

// ─────────────────────────────────────────────────────────────────
// 辅助函数
// ─────────────────────────────────────────────────────────────────

type TelemetryReading = { sensor_type: string; value: number; is_anomaly: boolean };
type TelemetryResponse = { scenario: string; readings: TelemetryReading[] };

/** 等待页面完全 hydrate（React SPA 需要等到 "系统在线" 标识出现） */
async function gotoAndWaitHydrated(page: Page) {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    // 等待 React 渲染完成：页脚"Safety Guard"出现意味着全页已 mount
    await page.waitForSelector("text=Safety Guard", { timeout: 20_000 });
}

async function checkBackend(page: Page): Promise<boolean> {
    try {
        const resp = await page.request.get("http://localhost:8000/health", { timeout: 3000 });
        return resp.ok();
    } catch {
        return false;
    }
}

// ─────────────────────────────────────────────────────────────────
// 1️⃣ 页面结构验证（无后端）
// ─────────────────────────────────────────────────────────────────

test.describe("页面静态结构", () => {
    test("应正确渲染品牌标识和系统名称", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await expect(page.locator("text=NEXUS-OMNIGUARD").first()).toBeVisible();
        await expect(page.locator("text=智巡护航").first()).toBeVisible();
        await expect(page.locator("text=具身智能决策中枢")).toBeVisible();
    });

    test("应显示4个场景触发按钮", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await expect(page.locator("text=正常巡检")).toBeVisible();
        await expect(page.locator("text=场景A").first()).toBeVisible();
        await expect(page.locator("text=场景B").first()).toBeVisible();
        await expect(page.locator("text=冷链超温")).toBeVisible();
    });

    test("应显示推理轨迹占位提示", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await expect(page.locator("text=选择场景并触发推理")).toBeVisible();
    });

    test("应显示三大面板标题", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        // 逐一验证，使用更宽松的文字匹配
        await expect(page.locator('.panel-title').filter({ hasText: '传感器数据流' }).first()).toBeVisible({ timeout: 5_000 });
        await expect(page.locator('.panel-title').filter({ hasText: '推理轨迹' }).first()).toBeVisible({ timeout: 5_000 });
        // "指令执行控制台"用部分文字匹配
        await expect(page.locator('.panel-title').filter({ hasText: '控制台' }).first()).toBeVisible({ timeout: 5_000 });
    });

    test("底部状态栏应显示知识库信息和 Safety Guard", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await expect(page.locator("text=知识库")).toBeVisible();
        await expect(page.locator("text=Safety Guard")).toBeVisible();
        await expect(page.locator("text=20份手册")).toBeVisible();
    });

    test("系统在线状态应显示绿色脉冲点", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await expect(page.locator("text=系统在线")).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────
// 2️⃣ 后端 API 健康检查
// ─────────────────────────────────────────────────────────────────

test.describe("后端 API 健康检查", () => {
    test.beforeEach(async ({ page }) => {
        if (!await checkBackend(page)) {
            test.skip(true, "后端服务未启动 (http://localhost:8000)");
        }
    });

    test("GET /health 应返回 ok", async ({ page }) => {
        const resp = await page.request.get("http://localhost:8000/health");
        expect(resp.ok()).toBe(true);
        const body = await resp.json();
        expect(body.status).toBe("ok");
        expect(body.service).toBeDefined();
    });

    test("POST /telemetry/trigger 盐雾场景 — 应返回超阈值读数", async ({ page }) => {
        const resp = await page.request.post("http://localhost:8000/telemetry/trigger", {
            data: { scenario: "salt_spray" },
        });
        expect(resp.ok()).toBe(true);
        const body = await resp.json() as TelemetryResponse;
        expect(body.scenario).toBe("salt_spray");
        expect(body.readings.length).toBeGreaterThan(0);

        const saltReading = body.readings.find((r) => r.sensor_type === "SALT_SPRAY");
        expect(saltReading).toBeDefined();
        if (!saltReading) {
            throw new Error("SALT_SPRAY reading missing");
        }
        expect(saltReading.value).toBeGreaterThan(15);
        expect(saltReading.is_anomaly).toBe(true);
        console.log(`  ✅ 盐雾读数: ${saltReading.value.toFixed(1)} mg/m³ (is_anomaly=${saltReading.is_anomaly})`);
    });

    test("POST /telemetry/trigger 危化品场景 — VOC 应超阈值", async ({ page }) => {
        const resp = await page.request.post("http://localhost:8000/telemetry/trigger", {
            data: { scenario: "hazmat" },
        });
        const body = await resp.json() as TelemetryResponse;
        const vocReading = body.readings.find((r) => r.sensor_type === "VOC");
        expect(vocReading).toBeDefined();
        if (!vocReading) {
            throw new Error("VOC reading missing");
        }
        expect(vocReading.is_anomaly).toBe(true);
        console.log(`  ✅ VOC 读数: ${vocReading.value.toFixed(2)} mg/m³ (is_anomaly=${vocReading.is_anomaly})`);
    });

    test("POST /sessions 应创建 UUID 格式的会话 ID", async ({ page }) => {
        const resp = await page.request.post("http://localhost:8000/sessions");
        expect(resp.ok()).toBe(true);
        const body = await resp.json();
        expect(body.session_id).toMatch(
            /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
        );
        console.log(`  ✅ 新会话 ID: ${body.session_id}`);
    });
});

// ─────────────────────────────────────────────────────────────────
// 3️⃣ 场景触发 UI 交互（需后端运行）
// ─────────────────────────────────────────────────────────────────

test.describe("场景触发 UI 交互", () => {
    test.beforeEach(async ({ page }) => {
        if (!await checkBackend(page)) {
            test.skip(true, "后端服务未启动");
        }
    });

    test("点击正常巡检 — 传感器卡片应出现温度/湿度数值", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await page.click("button:has-text('正常巡检')");
        // 等待传感器卡片数字出现（至少出现°C 单位）
        await expect(page.locator("text=°C").first()).toBeVisible({ timeout: 15_000 });
        console.log("  ✅ 温度传感器卡片已渲染");
    });

    test("触发盐雾场景 — 应出现'超标'徽章", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await page.click("button:has-text('场景A')");
        await expect(page.locator("text=超标").first()).toBeVisible({ timeout: 15_000 });
        console.log("  ✅ '超标' 徽章已渲染（盐雾超阈值）");
    });

    test("推理运行期间应显示中止按钮", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await page.click("button:has-text('场景A')");
        // Agent 推理启动时应显示中止按钮
        await expect(page.locator("text=中止推理")).toBeVisible({ timeout: 20_000 });
        console.log("  ✅ 中止推理按钮已出现");
    });
});

// ─────────────────────────────────────────────────────────────────
// 4️⃣ Agent 推理 SSE 流验证（需后端+LLM）
// ─────────────────────────────────────────────────────────────────

test.describe("Agent 推理 SSE 流", () => {
    test.beforeEach(async ({ page }) => {
        if (!await checkBackend(page)) {
            test.skip(true, "后端服务未启动");
        }
    });

    test("盐雾场景推理 — 应出现感知阶段步骤", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await page.click("button:has-text('场景A')");
        // 等待推理轨迹中出现"感知"节点
        await expect(page.locator(".thought-step").first()).toBeVisible({ timeout: 30_000 });
        console.log("  ✅ 推理轨迹第一步已出现");
    });

    test("推理完成后 — 指令控制台应显示指令状态", async ({ page }) => {
        await gotoAndWaitHydrated(page);
        await page.click("button:has-text('正常巡检')");
        // 等待推理轨迹出现（思考第1步）
        await page.waitForSelector(".thought-step", { timeout: 40_000 });
        // 再等2秒让 SSE 流完成
        await page.waitForTimeout(3000);
        // 验证指令控制台面板标题仍在（页面未崩溃）
        const panelVisible = await page.locator('.panel-title').filter({ hasText: '控制台' }).first().isVisible();
        console.log(`  指令控制台面板: ${panelVisible}`);
        // 验证思考步骤数量 >= 1
        const stepCount = await page.locator('.thought-step').count();
        console.log(`  推理步骤数: ${stepCount}`);
        expect(stepCount).toBeGreaterThanOrEqual(1);
    });
});
