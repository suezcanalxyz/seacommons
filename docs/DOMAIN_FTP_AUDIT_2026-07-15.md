# Domain, redirect and FTP audit — 15 July 2026

## Actual hosting map

| Name | Current destination | Deployment source |
|---|---|---|
| `suezcanal.xyz` | Aruba Windows hosting, `31.11.35.226` | FTP `/suezcanal.xyz` |
| `www.suezcanal.xyz` | Aruba Windows hosting | Same FTP root |
| `seacommons.suezcanal.xyz` | Vercel CNAME | SeaCommons Vercel project |
| `seacommons.org` | Aruba placeholder, `62.149.128.40` | No matching FTP root found |
| New SeaCommons hosts | Pending DNS | Oracle `204.216.210.155` |

The FTP credential found in Downloads can access only the `suezcanal.xyz` tree and Aruba backup
directories. It cannot access `/seacommons.org` or `/www.seacommons.org`. This does not block the
migration because `seacommons.org` will be served by Oracle after its A records are changed.

## Redirect finding

There is currently no redirect from `seacommons.suezcanal.xyz` to `seacommons.org`:

- DNS is a CNAME to Vercel;
- HTTP redirects only to HTTPS on the same hostname;
- HTTPS returns the existing demo with status 200;
- the Aruba `web.config` contains no SeaCommons redirect rule.

DNS records select a destination; they do not create an HTTP 301 redirect. If the old hostname is
to be retired, first validate DNS, TLS, login and simulation on `seacommons.org`, then point the old
hostname to Oracle and let Nginx return a permanent redirect. Deleting the old record without a
redirect would break bookmarks and indexed links.

## FTP and credential findings

1. The FTP password and username are embedded in two tracked source files. Because they are in Git
   history, removing the current lines is not sufficient: the Aruba credential must be rotated.
2. Three Google Search Console/OAuth credential files in the public Aruba web root return HTTP 200.
   Remove them immediately and revoke/rotate the associated OAuth client and refresh token.
3. `/suezcanal.xyz/seacommons` is a stale April 2026 application copy and is unrelated to the live
   Vercel subdomain. It includes an environment file; IIS currently blocks that file over HTTP, but
   the unused tree should be archived and removed.
4. The deploy script uses unencrypted FTP. Aruba documents FTPS and IP allowlisting; migrate the
   script to the secure mode and restrict FTP access to trusted IPs.
5. The FTP deploy currently excludes some developer files, but the remote root already contains
   editor, OAuth, diagnostic and temporary artifacts. Replace additive upload with an explicit
   publish manifest and a reviewed cleanup list.

## Recommended order

1. Remove the three public Google credential files and revoke/rotate their credentials.
2. Rotate the Aruba FTP/account password.
3. Replace inline credentials with a local encrypted credential file excluded from Git.
4. Enable FTPS and Aruba's FTP IP restriction.
5. Archive and remove the stale remote `seacommons` tree and temporary files.
6. Change the `seacommons.org` DNS records to Oracle and complete TLS acceptance.
7. Only after acceptance, migrate the legacy subdomain from Vercel to an Oracle/Nginx 301 redirect.

## Cleanup performed

- The three publicly downloadable Google OAuth/Search Console files were deleted from Aruba FTP
  and now return HTTP 404.
- The stale SeaCommons `.env` was deleted from the Aruba FTP tree.
- Inline FTP credentials were removed from the current deployment script. It now reads credentials
  from environment variables or requests them interactively with a secure password prompt.
- Two legacy batch files containing inline credentials were deleted.
- Git history for `main` and the former PR source branch was rewritten and force-pushed. The
  password has zero occurrences in the rewritten reachable branch history.
- The repository is private and has no forks.
- GitHub still retains the old commit through the read-only internal ref `refs/pull/1/head`. GitHub
  Support must dereference PR #1 and run garbage collection to remove that final cached reference.
- Password rotation was deliberately deferred at the owner's request. Until it is rotated, it must
  still be considered compromised.
