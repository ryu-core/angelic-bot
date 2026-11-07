import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__XIEL_SOCKET_FACTORY__ = () => ({
      on() {
        return this;
      },
      connect() {
        return this;
      },
      disconnect() {
        return this;
      },
    });
  });
});

const status = {
  online: true,
  guilds: 42,
  users: 125000,
  latency: 38,
  uptime: 86400,
  commandCount: 140,
  commandsRun: 9800,
  updatedAt: "2026-07-23T00:00:00.000Z",
};

async function installPublicApi(page, user = null) {
  await page.route("**/api/auth/me", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ data: user }),
  }));
  await page.route("**/api/status", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ data: status }),
  }));
  await page.route("**/api/commands", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ data: [] }),
  }));
}

test("public routes expose a single primary heading and never load the Saturn video off Home", async ({ page }) => {
  await installPublicApi(page);
  const saturnVideoRequests = [];
  const routeTitles = {
    "/invites": "Invite control · xiel",
    "/commands": "Commands · xiel",
    "/docs": "Documentation · xiel",
    "/status": "System status · xiel",
    "/privacy": "Privacy · xiel",
    "/terms": "Terms of service · xiel",
  };
  page.on("request", (request) => {
    if (request.url().includes("/media/xiel-saturn-clean.mp4")) saturnVideoRequests.push(request.url());
  });

  for (const [path, title] of Object.entries(routeTitles)) {
    await page.goto(path);
    const heading = page.locator("h1");
    await expect(heading).toHaveCount(1);
    await expect(page).toHaveTitle(title);
  }

  await page.goto("/commands");
  const docsLink = page.getByRole("link", { name: "Docs", exact: true });
  await expect(docsLink).toHaveCount(1);
  await docsLink.click();
  await expect(page.locator("h1")).toBeFocused();

  expect(saturnVideoRequests).toEqual([]);
});

test("dashboard remains usable at 320px with defensive guild content", async ({ page }) => {
  await installPublicApi(page, { id: "1", username: "Operator", avatar: null, role: "user" });
  await page.route("**/api/servers", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      data: [{ id: "123", name: "A very long managed Discord server name for responsive testing", icon: null, memberCount: null }],
    }),
  }));
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(horizontalOverflow).toBe(false);
});

test("reduced motion uses the static Saturn poster without loading video", async ({ page }) => {
  await installPublicApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const saturnVideoRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/media/xiel-saturn-clean.mp4")) saturnVideoRequests.push(request.url());
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(".saturn-scroll-scene--static")).toBeVisible();
  expect(saturnVideoRequests).toEqual([]);
});

test("public-only mode explains why administrator sign-in is unavailable", async ({ page }) => {
  await installPublicApi(page);
  await page.goto("/?error=dashboard_unavailable");

  await expect(page.getByRole("alert")).toContainText("public site is online");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Shape chaos/);
});

test("compact navigation closes with Escape and restores trigger focus", async ({ page }) => {
  await installPublicApi(page);
  await page.setViewportSize({ width: 680, height: 800 });
  await page.goto("/");

  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Primary navigation" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Primary navigation" })).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("public API failure preserves the route and exposes retry feedback", async ({ page }) => {
  await installPublicApi(page);
  await page.route("**/api/commands", (route) => route.abort("internetdisconnected"));
  await page.goto("/commands");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Every command. Searchable.");
  await expect(page.getByRole("alert")).toContainText("The service could not be reached. Try again.");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();

  await page.goto("/docs");
  await expect(page.getByRole("heading", { name: "Getting started" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("The service could not be reached. Try again.");
  expect(await page.getByText("unavailable", { exact: true }).count()).toBeGreaterThanOrEqual(4);
});

test("status failure exposes its existing refresh action", async ({ page }) => {
  await installPublicApi(page);
  await page.route("**/api/status", (route) => route.abort("internetdisconnected"));
  await page.goto("/status");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("System status");
  await expect(page.getByRole("alert")).toContainText("The service could not be reached. Try again.");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("critical routes reflow at every release and zoom-equivalent width", async ({ page }) => {
  test.slow();
  await installPublicApi(page, { id: "1", username: "Operator", avatar: null, role: "user" });
  await page.route("**/api/servers", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      data: [{ id: "123", name: "Citadel Prime", icon: null, memberCount: 42 }],
    }),
  }));
  await page.emulateMedia({ reducedMotion: "reduce" });

  for (const width of [320, 360, 680, 720, 1000, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/commands", "/dashboard"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflow, `${path} overflowed at ${width}px`).toBe(false);
    }
  }
});

test("runtime reduced-motion changes disable active page motion", async ({ page }) => {
  await installPublicApi(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/privacy");

  const stage = page.locator(".route-stage");
  await expect(stage).toBeVisible();
  expect(await stage.evaluate((element) => getComputedStyle(element).animationName)).not.toBe("none");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(
    () => stage.evaluate((element) => getComputedStyle(element).animationName),
  ).toBe("none");
});
