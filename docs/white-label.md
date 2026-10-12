# White-label: how a company customizes look and feel

An organization administrator can give their company its own name, colors, fonts and logos. Employees see
that identity in the desktop client before and after they sign in. Nothing else about the product changes,
and a company that sets nothing keeps the Prometheon default.

## Quick path (administrator)

1. Sign in to the admin console (`/admin/`) and pick your organization.
2. Open **Branding**.
3. Set the product name and login message, three colors and two fonts. Optionally upload up to three logos.
4. Watch the live preview: the client **sign-in screen** in **Light** and **Dark**, and the **browser tab**
   (company name and icon). They update as you type; the rest of the page waits for a save.
5. **Save branding**. Employees get it on their next launch or sign-in, and running clients pick it up within
   about 5 minutes.
6. Give employees your **company code**. The Branding page shows it at the top, with a **Copy company code**
   button (for example `org-a`). They type it once, the first time they open the app.

Made a mistake? **Reset to default** publishes the Prometheon look as a new revision. Nothing is ever lost:
every save and reset is kept in the revision history.

## What you can set

| Setting | Rule |
|---------|------|
| Product name | 1 to 40 plain characters. No `< > { } \` `` ` `` or control characters. |
| Login message | Up to 280 plain characters (may be empty). Same character rules. |
| Primary color | `#RRGGBB`, at least 3:1 contrast against white. |
| Accent color | `#RRGGBB`, at least 3:1 contrast against white. |
| Background tint | `#RRGGBB`, light enough to carry dark text. |
| Heading and body font | One of Inter, Montserrat, Source Sans 3, IBM Plex Sans, Nunito Sans, Roboto. |

You choose **three colors**; the app derives every light and dark shade from them and checks that text stays
readable. The page checks this with the same generator the server uses, **as you type**: a color that is not
readable is explained right beside its field, before you press Save. The check never replaces the server: if a
combination cannot be made readable, **the server still refuses the save** and says so. Fonts are bundled with
the apps, so there is nothing to host.

## The live preview

| Part | What it shows |
|------|---------------|
| Sign-in screen (Light and Dark) | The client sign-in as employees see it: company mark and name, "Welcome to your company", your login message, the email and password fields, the **Sign in** button. |
| Browser tab | The tab title (your product name) and the icon (your isotipo, or the Prometheon icon when none is set). |

The preview is only a picture: it has no working fields and nothing in it is saved until you press **Save branding**.

## Logos

| Slot | Used for |
|------|----------|
| Logo for light backgrounds | Wordmark on light screens |
| Logo for dark backgrounds | Wordmark on dark screens |
| Isotipo (square mark) | The mark beside the product name and other small spaces |

| Rule | Limit |
|------|-------|
| Format | PNG or WebP only. SVG is refused, because it can carry scripts. |
| Size | At most 256 KB per file. |
| Dimensions | 16 to 1024 pixels per side. |
| Storage | At most 24 distinct images per organization. |
| Cleaning | The server re-writes the file keeping only image data. Metadata is dropped. |

An uploaded image goes live only when you save. Replaced images stop being served at once.

## How the apps pick the branding

| Moment | What happens |
|--------|--------------|
| First launch | The client asks for the **company code**, then shows that company's colors, name, logo, tab title and icon before any sign-in. |
| Later launches | The remembered branding appears immediately, then is refreshed in the background. |
| Offline or server down | The last valid branding stays. A client that never saw one shows the Prometheon default. |
| After sign-in | The brand follows the **organization you open**. A person who belongs to several organizations sees each one's own look when they switch. |
| Wrong or unknown code | One generic "Company not found" message. The screen never reveals which companies exist. |

The client treats everything it receives as untrusted: it checks the exact shape, applies colors one value at
a time (never as injected style text), and falls back to the default if anything does not validate.

## Try it locally

`scripts\mvp-local.ps1` seeds two companies with their own branding (revision 1), so a fresh stack shows two
different identities. The Prometheon default stays the fallback for any organization without branding.

| Company code | Organization | Branding |
|--------------|--------------|----------|
| `org-a` | Organization A | Northwind Logistics: blue and amber, Source Sans 3 / Roboto, ring mark |
| `org-b` | Organization B | Lumen Finance: purple and orange, IBM Plex Sans / Nunito Sans, diamond mark |

`scripts\branding-smoke.ps1` proves this on the real stack: it starts the owned stack, checks both
identities in the admin console and the client, and removes everything it started.

## Limits to know

- The company code is public by design (it is how a client finds a company). Looking codes up is
  rate-limited and unknown, closed and malformed codes all answer the same way.
- The rate limiter lives in the single control-plane process. A deployment with several instances needs a
  shared limiter in front.
- Branding is cosmetic. It never changes who can sign in or what a member can access.

## Checklist

- [ ] The primary and accent colors are readable on white.
- [ ] Logos are PNG or WebP, under 256 KB.
- [ ] The save succeeded (the page shows the new revision number).
- [ ] Employees have the company code.

## Next step

Design and decisions: `openspec/changes/v1-white-label/`. Local stack and admin e2e: `docs/mvp-local.md`.
