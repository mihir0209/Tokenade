"""Quick headless test: inject cookies + localStorage from Firefox into CloakBrowser."""

import asyncio
import json
import sys
sys.path.insert(0, "/home/ghostrider/Projects/tokenade")

from cloakbrowser import launch_async
from tokenade.core.importer.cookie_extractor import CookieExtractor
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery


def get_firefox_path():
    discovery = BrowserProfileDiscovery()
    profiles = discovery.discover_all()
    for bn, bp in profiles.items():
        if bn == "firefox":
            for p in bp:
                return str(p.path)
    return None


def convert_cookie(c):
    pw = {
        "name": c.get("name", ""),
        "value": c.get("value", ""),
        "domain": c.get("domain", ""),
        "path": c.get("path", "/"),
        "secure": c.get("secure", False),
        "httpOnly": c.get("httpOnly", False),
        "sameSite": "None",
    }
    expires = c.get("expires", 0)
    if expires and int(expires) > 0:
        exp = int(expires)
        if exp > 1262304000000:
            exp = exp // 1000000
        pw["expires"] = exp
    else:
        pw["expires"] = -1
    return pw


async def test_site(browser, context, site_name, cookie_domains, nav_url, ls_key=None):
    """Test a single site."""
    firefox_path = get_firefox_path()
    extractor = CookieExtractor(firefox_path, browser="firefox")
    all_cookies = extractor.extract()

    # Inject cookies
    site_cookies = [
        c for c in all_cookies
        if any(d in c.get("domain", "") for d in cookie_domains)
    ]
    if site_cookies:
        pw_cookies = [convert_cookie(c) for c in site_cookies]
        await context.add_cookies(pw_cookies)

    # Inject localStorage if needed
    if ls_key:
        ls = LocalStorageExtractor(firefox_path, browser="firefox")
        origin = f"https://{ls_key}"
        try:
            ls_data = ls.extract(origin_filter=ls_key)
            if ls_data:
                # Store for later injection
                pass
        except Exception:
            pass

    # Navigate
    page = await context.new_page()
    try:
        await page.goto(nav_url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        title = await page.title()
        url = page.url
        print(f"\n{'='*60}")
        print(f"{site_name}")
        print(f"  Cookies injected: {len(site_cookies)}")
        print(f"  Title: {title}")
        print(f"  URL: {url[:80]}")

        # Check for login indicators
        logged_in_selectors = {
            "Google": ["img.gbii", "a[aria-label*='Google Account']", "#gb"],
            "GitHub": ["img.avatar", "[data-testid='header-avatar']"],
            "Discord": ["[data-list-item-id='guildsnav']", ".guilds-wrapper"],
            "Reddit": ["#header-account-action-button"],
        }

        logged_in = False
        for sel in logged_in_selectors.get(site_name, []):
            try:
                el = await page.query_selector(sel)
                if el:
                    logged_in = True
                    print(f"  ✅ LOGGED IN (selector: {sel})")
                    break
            except:
                pass

        if not logged_in:
            # Check for login form
            login_sels = [
                "input[type='email']", "input[name='email']",
                "input[name='username']", "form[action*='login']",
                "a[href*='login']",
            ]
            for sel in login_sels:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        print(f"  ❌ NOT LOGGED IN (login form: {sel})")
                        break
                except:
                    pass
            else:
                print(f"  ❓ Status unknown (no selectors matched)")

    except Exception as e:
        print(f"\n{site_name}: ERROR {str(e)[:100]}")

    await page.close()


async def main():
    print("Starting CloakBrowser E2E test...")
    print("Injecting Firefox cookies into CloakBrowser headless...")

    browser = await launch_async(headless=True)
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})

    # Test each site
    await test_site(browser, context, "Google", [".google.com"], "https://mail.google.com")
    await test_site(browser, context, "GitHub", [".github.com"], "https://github.com")
    await test_site(browser, context, "Discord", [".discord.com", "discordapp.com"], "https://discord.com")
    await test_site(browser, context, "Reddit", [".reddit.com"], "https://www.reddit.com")

    # Test Telegram (localStorage-based)
    firefox_path = get_firefox_path()
    ls = LocalStorageExtractor(firefox_path, browser="firefox")
    telegram_ls = ls.extract(origin_filter="web.telegram.org")

    if telegram_ls:
        print(f"\n{'='*60}")
        print("Telegram")
        print(f"  localStorage keys: {len(telegram_ls)}")
        print(f"  Keys: {list(telegram_ls.keys())[:10]}")

        # Inject localStorage via init script
        token_json = json.dumps(telegram_ls.get("user_auth", ""))
        init_script = f"""
        (function() {{
            var origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function() {{
                this._url = arguments[1];
                origOpen.apply(this, arguments);
            }};
        }})();
        """
        await context.add_init_script(init_script)

        page = await context.new_page()
        try:
            await page.goto("https://web.telegram.org", timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            # Try to set localStorage
            for key, val in telegram_ls.items():
                val_json = json.dumps(val)
                try:
                    await page.evaluate(f'() => {{ localStorage.setItem("{key}", {val_json}); }}')
                except:
                    pass

            await page.reload(timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            title = await page.title()
            print(f"  Title: {title}")

            # Check for chat list
            chat = await page.query_selector(".chat-list")
            if chat:
                print(f"  ✅ LOGGED IN (selector: .chat-list)")
            else:
                auth_form = await page.query_selector(".auth-form")
                if auth_form:
                    print(f"  ❌ NOT LOGGED IN (selector: .auth-form)")
                else:
                    print(f"  ❓ Status unknown")

        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")
        await page.close()

    await browser.close()
    print(f"\n{'='*60}")
    print("Test complete.")

asyncio.run(main())
