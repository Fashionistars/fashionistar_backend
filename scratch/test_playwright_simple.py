import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    print("Starting Playwright...")
    async with async_playwright() as p:
        print("Launching Chromium...")
        try:
            browser = await p.chromium.launch(headless=True)
            print("Creating browser context...")
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            
            url = "https://fashionistar-frontend-259415881346.europe-west1.run.app"
            print(f"Navigating to {url}...")
            await page.goto(url, timeout=30000, wait_until="networkidle")
            
            print("Successfully navigated! Page title:", await page.title())
            
            output_dir = r"C:\Users\FASHIONISTAR\OneDrive\Documenti\FASHIONISTAR_ANTAGRAVITY\FASHIONISTAR_REAL_VISION_BROWSER_TESTING\test-evidence"
            os.makedirs(output_dir, exist_ok=True)
            screenshot_path = os.path.join(output_dir, "unauth_homepage_hero.png")
            
            print(f"Taking screenshot and saving to {screenshot_path}...")
            await page.screenshot(path=screenshot_path, full_page=True)
            print("Screenshot saved successfully!")
            
            await browser.close()
        except Exception as e:
            print("Error occurred:", e)

if __name__ == "__main__":
    asyncio.run(main())
