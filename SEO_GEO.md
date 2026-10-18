# Search and content maintenance

The 2026-10-18 change preserves canonical URLs, titles, descriptions, original
body/map photographs, bottom galleries, image order and source verification dates.
It consolidates consultation questions with their answer records, joins unconfirmed
grade preparation with the existing consultation section, and replaces only exact
school-reference duplicates with a link to the complete retained explanation.
Repeated subject/grade lists, masked teacher names and separate school regions are
valid information and must not be removed as automatic duplicates.

Build the reviewed snapshot through all stages in `vercel.json`. The final
`seo-geo-build.mjs` stage has no network calls and adds no browser JavaScript.
Run it with `--dry-run` for inspection, or `--report=PRIVATE_PATH.json` to record
final page hashes. Dates represent this editorial revision, never the build clock.

Before releasing, compare all sitemap pages with the last production snapshot:
image and iframe tags/order, anchor IDs, link destinations, source facts, visible
text retention, canonical/robots, JSON-LD and changed-only sitemap dates. Check
responsive menus, search, disclosure elements, map and original-image zoom using
representative pages. After deployment, GET every sitemap URL and compare against
the final local build; verify the production domain, deployment and commit.

## IndexNow

`indexnow-config.json` contains a public ownership key, not an authentication
secret. Its matching text file is included in the reviewed public manifest.
Keep private notification state outside the public directory. Initialization must
follow complete production GET verification and sends no historical URL batch:

    node notify-indexnow.mjs --initialize --report=PRIVATE_BUILD_REPORT.json --validation=PRIVATE_PRODUCTION_HTTP_REPORT.json --state=PRIVATE_STATE.json

After a later verified release, replace `--initialize` with `--dry-run` to review
the queue, then with `--notify` to submit it.
Only added, changed or removed URLs relative to that baseline are submitted.
Do not run notifications from a build or preview, or initialize again to conceal
pending changes. HTTP 200/202 acknowledges notification, not crawling or indexing.
This is an explicit release step; it is not a scheduled task or automatic GitHub
workflow. Official reference: https://searchadvisor.naver.com/guide/indexnow-faq

Search Advisor crawl/index data, public HTTP eligibility, search impressions,
rank and AI source citations are separate evidence. No markup or notification
guarantees search position or AI citation.

The `local-content-build.mjs` stage enriches existing consultation areas
from exact curriculum rows and teacher profiles already linked to each branch.
It preserves source dates, branch facts, URLs and image/map positions. Unknown
profiles and course availability must never be inferred from similar names.
Its `.local-content-report.json` records that intermediate output. Validate every
new profile anchor against the source page, and every added schema citation
against the corresponding visible link. The source workbooks remain unchanged.

The final `content-refinement-build.mjs` stage consolidates exact repeated
school lists and course qualifications. Subject-grade facts, distinct teachers,
images, maps and visible source dates remain intact. Shared qualifications must
retain explicit subject scope. FAQ changes must match visible answers and keep
the full school reference list in the main body. Missing operating information
must remain unconfirmed; preparation examples are not availability claims.
Use `.content-refinement-report.json` as the final hash and IndexNow report.
`release-build.mjs` runs every existing stage in that order and stops on failure;
the short Vercel entry point avoids its 256-character build-command limit.
