# What the accessible table should do (accessible_table.py), checked by every table drill

| Rule | Source | Check |
|---|---|---|
| Table: arrows move by cell, column kept on Up/Down, row kept on Left/Right | 261-291 | Walk rows and columns; edges stay put |
| Table cell speech: "row, column, value"; first column "column, value" | 449-459 | Exact text against ESPN |
| Quick List: comma-separated values, one row per item | 382 | Exact text against ESPN |
| Full List: "Header: Value; ..." for every column | 388-391 | Exact text; a short row must not lose columns silently |
| Alt+V cycles Table, Quick, Full; Alt+T/Q/F go direct; same mode does nothing | 148-181 | Each key, from each mode |
| Row kept across a switch; column returns to 0 | 213-226 | Move to row N, column M, switch, read |
| Keys work anywhere in the dialog | event filter is on the table only, 136-139 | Press from tab bar, Close button |
| Mode saved and used for new tables | 194 | MODE=0,1,2 clips, reopened dialog, other tabs |
| Saved Quick or Full List: data present, focus in the list, a current row | 184, 561-562, 363-366 | Arrive with no extra key; first Down reads row 1 or 2, not nothing |
| Tables filled by setItem get synced lists | 527-531 | Teams, Leaders in saved list modes |
| Description doesn't grow | 250-252 | Switch to the same mode twice |
| Tab leaves the table without an empty stop | 133, 294-296 | Count Tab stops |
