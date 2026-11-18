# SeaCommons Paperclip pilot

Run this pilot on a workstation or staging host with outbound HTTPS access to `live.seacommons.org`. Paperclip listens on loopback and stores its database separately from SeaCommons.

Start the pinned Paperclip version in one terminal:

```sh
npx paperclipai@2026.1106.0 onboard --yes --bind loopback --no-install-service
```

From the repository root in another terminal:

```sh
node scripts/paperclip/setup.mjs --run
```

The setup reuses the same company, agent and routine on repeat invocations. The routine is manual and uses Paperclip's Process adapter with no model credentials. Check the run output in Paperclip's activity view.

The probe samples up to three distinct MMSIs from the public maritime feed and reports the last fix timestamp exposed by each public dossier. A sample verifies API availability and reports whether the dedicated latest-fix field exists. A missing case or a network failure cannot verify movement. Verifying map and report updates on two successive fixes requires a separate browser check.
