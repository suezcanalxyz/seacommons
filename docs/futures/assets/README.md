# Futures partner asset registry

This directory is an interim, versioned upload location for presentations, briefs and
other *non-sensitive* partner materials. Only repository collaborators can access it.

## Upload workflow (interim)
1. Use GitHub's **Add file → Upload files** in this directory on a new branch.
2. Use descriptive kebab-case names, such as `seacommons-pilot-brief-2026-10.pdf`.
3. Submit a pull request with purpose, audience, owner, version, visibility and
   a one-paragraph summary. Avoid personal or sensitive maritime case data.
4. After review, add a resource entry in
   `apps/web/src/futures/data.js` to surface it in the Futures Docs catalogue.
5. Mark superseded material and preserve a canonical current edition.

GitHub uploads are *not* an in-app upload API. They require repository write access,
and the catalogue currently needs an editorial commit. Browser-upload, automatic
indexing, durable metadata, granular grants, signed download URLs and retention
must be implemented with a private document service and server-verified membership
before inviting external partners.

Never place confidential records in the web public assets directory. Storage and
resource access controls are not implied by the fact that Futures has an OIDC login.
