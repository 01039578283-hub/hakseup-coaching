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

The `learning-levels-build.mjs` stage replaces the exact common prompt in
existing curriculum entries with a link to grouped elementary/middle/high English
or mathematics questions. Its six groups use 18 reviewed rows of the supplied
curriculum workbook, with source target/sequence/task and authored questions.
Render one group per relevant school band and subject within each existing
preparation area. Native disclosures include their full content in initial HTML.
Keep learning examples distinct from actual classes, enrollment or teacher
assignment, and retain the optional-activity boundary for grade 1/2 English.
Existing grade tasks, curriculum links, local facts, images/maps, teacher records,
FAQ and earlier role-specific prose remain intact. Use
`.learning-levels-report.json` as its intermediate report.

The final `navigation-refresh-build.mjs` stage groups the six existing homepage
directory cards into three reader purposes and adds school-stage shortcuts.
Mapped detail pages receive an early table of contents linking to their actual
facts, directions, preparation, FAQ and related materials. Existing subject
tables of contents move intact into a native disclosure in the new guide.
Existing branch hero shortcuts also move intact into that guide's secondary
disclosure, avoiding two consecutive sets of navigation buttons.
Keep all original page URLs, fact paragraphs, old anchor IDs, link destinations,
image/map tags and relative image order. Never infer new branch facts from the
navigation labels. Source verification dates remain unchanged; only the actual
edited pages receive the 2026-10-27 editorial/sitemap date. The new stylesheet is
content-addressed in the existing immutable CSS directory and adds no JavaScript.
Use `.navigation-refresh-report.json` for final hashes. Validate every new anchor
and branch link, initial HTML content, keyboard/mobile use and unchanged pages.
# 2026-10-27: 미색인 동네 페이지의 구체적인 답변

`local-answer-build.mjs` runs after the navigation stage. Its explicit, reviewed
cohort is 73 neighborhood detail URLs appearing in Search Console's 2026-10-23
"Crawled - currently not indexed" examples, plus their 24 actual branch pages.
The other 25 examples are directory hubs and are outside this content change.
Being in this report is a prioritization signal, not proof of a content defect.

`local-answer-config.json` records the exact paths, branch mapping, public facts,
workbook hash and source cells. `local-answer-notes.json` contains reviewed copy.
The current center workbook takes precedence over the older summary CSV where
they disagree; existing conditional or unconfirmed course status is retained.
The source's internal marketing and staff instructions are not public copy.

The stage replaces only bounded editorial text: the neighborhood's direct answer,
branch-specific enrollment decisions, school-material checklists and consultation
outcomes. Repeated school names in FAQ answers link to their retained reference
list. Branch pages explain source-specific conditions and the record to keep
after consultation. Visible FAQ answers and their JSON-LD stay identical.
No URL, title, description, canonical, media, map, logo or existing link is removed.
No new CSS or JavaScript is added. Unselected pages are byte-identical. The private
build report lists every old/new text replacement for preservation validation.

Release checks: all public URLs and referenced resources, source/media retention,
all changed FAQ pairs, responsive branch and neighborhood samples, then the
Git-linked preview and actual production domain. Deployment, eligibility for
crawling, actual Google/Naver indexing and AI citations are separate results.

# 2026-10-27: previously excluded directory hubs

`hub-content-build.mjs` runs last and changes only the 25 directory URLs in
`hub-content-config.json`: one national, eight region and sixteen city/district
hubs. This is the previously reviewed Google 2026-10-23 crawled-not-indexed
cohort, not a new indexing inspection or a claim that content caused exclusion.

Original whole-card anchors become accessible article cards with independent
heading and child anchors. National cards link to every listed city/district;
regional cards link their existing neighborhood previews; city cards link to
their actual elementary/middle/high detail URLs and matched branch conditions
and directions. These are literal initial-HTML links, with no new JavaScript.
Existing directory destinations, titles, descriptions, canonical, course facts,
all media, maps and other pages remain intact. Article card ordering still
matches the existing ItemList. Related reading links go to the specific guide
that their labels describe, instead of repeatedly linking to the guide index.

The 16 city hubs reference 60 distinct branches. Printed addresses match both
the current published branch facts and the center workbook's address column.
`용인백현점(모두)` is the workbook's explicit name for the existing 용인백현점
page; the exact address matches row 139. Do not silently generalize this alias.
The source workbook hash and row references are recorded in the configuration.
Regional notes distinguish same-named neighborhoods, shared branches and actual
addresses (for example the Songpa directory's Wirye branch in Seongnam).
Neighborhood counts are counts of this site's guidance pages, not inventories
of every local academy or claims of current recruitment. Existing shared
coaching descriptions are introduced as comparison questions rather than a
promise that every branch offers an identical service.

`.hub-content-report.json` is the final generated report. Compare initial HTML
and ItemList/card order, verify every new child/branch/guide destination and
source address, preserve all non-target HTML bytes and media assets, and check
mobile/desktop views. The small added stylesheet uses the established immutable
content-hash path; no original stylesheet is rewritten. Page and sitemap dates
reflect these actual edits. Verify preview and production commit/domain/HTML
separately from future crawling, indexing, rankings and AI citations.
