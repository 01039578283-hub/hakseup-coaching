# Public search-quality stage

Run `node search-quality-build.mjs` after the existing metadata/favicon pipeline.
The default input/output is `.public-release`; `--root=...` selects a different
reviewed public directory and `--report=...` saves a private validation receipt.
Neither this file, the module nor its configuration belongs in the public manifest.

The stage keeps the existing URLs and all body/map/gallery images. It moves the
three optional reading blocks into one section before the existing bottom gallery,
preserving their link destinations and anchor IDs. Unconfirmed grade pages are
explicitly listed in `search-quality-config.json`; they receive study-preparation
content without claiming that the branch offers those courses.

`modifiedDate` is the date of this reviewed content change, not a build timestamp.
`photoPaths` and `photoModifiedDate` record the already verified 2026-10-10 photo
release. Rebuilding or deploying the same source must not advance either date.
Keep source verification dates in the visible branch facts unchanged unless those
facts have actually been checked again. Future content revisions must update their
own reviewed change record rather than automatically dating every page as today.

CSS is copied to a SHA-256 URL after relative resource URLs are resolved. Only
these content-addressed assets receive immutable caching. HTML and sitemap/RSS
continue to revalidate. The release snapshot builder accepts existing generated
CSS only when its bytes match the hash in its filename; all other unreviewed
output remains an error.

Release validation must compare all sitemap HTML with the previous approved
snapshot, including image order/attributes/files, gallery markup, original link
targets and anchor IDs, canonical/robots, JSON-LD and preserved manuscript text.
Check representative mobile/desktop layouts and interactions, then verify the
deployed commit, domain, HTTP routes, cache headers and public HTML.
