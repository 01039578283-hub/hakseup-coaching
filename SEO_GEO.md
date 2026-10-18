# Search and content maintenance

The 2026-10-18 change preserves canonical URLs, titles, descriptions, original
body/map photographs, bottom galleries, image order and source verification dates.
It consolidates consultation questions with their answer records, joins unconfirmed
grade preparation with the existing consultation section, and replaces only exact
school-reference duplicates with a link to the complete retained explanation.
Repeated subject/grade lists, masked teacher names and separate school regions are
valid information and must not be removed as automatic duplicates.

Build the reviewed snapshot through all stages in `vercel.json`. The
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

The `content-refinement-build.mjs` stage consolidates exact repeated
school lists and course qualifications. Subject-grade facts, distinct teachers,
images, maps and visible source dates remain intact. Shared qualifications must
retain explicit subject scope. FAQ changes must match visible answers and keep
the full school reference list in the main body. Missing operating information
must remain unconfirmed; preparation examples are not availability claims.
Its `.content-refinement-report.json` records intermediate hashes.
`release-build.mjs` runs every existing stage in that order and stops on failure;
the short Vercel entry point avoids its 256-character build-command limit.

The `page-roles-build.mjs` stage revises existing editorial paragraphs,
without adding sections, styles, scripts or links. Neighborhood pages explain
the next course-selection decision; subject guides prepare student evidence;
branch and subject pages interpret their own listed grades; grade pages connect
their local school references to student-provided records. Center profiles turn
published teaching viewpoints into consultation questions, never confirmed
assignments or operating claims. Similarity screening excludes common navigation
and fact tables: its values are not search-engine duplicate/indexing scores.
Its `.page-roles-report.json` records intermediate hashes. Preserve
every other paragraph, all original links/IDs, source dates, FAQ/schema answers,
teacher/curriculum blocks and image/map tags in the production comparison.

The final `learning-levels-build.mjs` stage replaces the exact common prompt in
existing curriculum entries with a link to grouped elementary/middle/high English
or mathematics questions. Its six groups use 18 reviewed rows of the supplied
curriculum workbook, with source target/sequence/task and authored questions.
Render one group per relevant school band and subject within each existing
preparation area. Native disclosures include their full content in initial HTML.
Keep learning examples distinct from actual classes, enrollment or teacher
assignment, and retain the optional-activity boundary for grade 1/2 English.
Existing grade tasks, curriculum links, local facts, images/maps, teacher records,
FAQ and earlier role-specific prose remain intact. Use
`.learning-levels-report.json` as the final hash and IndexNow report.
