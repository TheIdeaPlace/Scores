# Screen reader test runs

Reports, findings logs and steps files from NVDA runs of the Windows app in the test VM. The steps files can be run again against a later build to compare speech. The recordings, ESPN snapshots and builds these were made from were kept in the OneDrive testing folder and cleared on Nov 7, 2026; only the text is kept here.

| Folder | What |
|---|---|
| `nvda-bugbash-2026-11-02/` | The first full NVDA bug bash: findings log, table contract, data audit and iOS check reports, and the steps files #158 refers to. |
| `nvda-live-ncaaf-2026-11-03/` | Live college football check. |
| `nvda-bugbash-2026-11-07-ncaaf/` | College football bug bash on 1.1.1. `README.md` is the report. Its findings became #202, #203 and #204, plus the Polls fix in #207. |
| `monitoring-2026-11-07/` | NVDA checks of the Live Scores Monitoring section (#186). |
| `jaws-stray-dialog-text-2026-11-08/` | JAWS repeating a closed dialog's text after the window title, fixed in #250. The first JAWS run, with exact JAWS speech from its speech history; a PyQt harness of the variants tried. |

The missing-data audit from Nov 3 is in `docs/audits/`.
