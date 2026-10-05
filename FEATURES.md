# Gems POS v13 — monthly/yearly stock, profit and exports

Update your existing WSL v12 installation (do not initialize another shop):

```bash
cd /root
unzip -o gems-pos-v13-reports.zip -d /root/
bash /root/gems-pos-v13-reports/apply-update.sh /root/gems-pos-wsl-v12
```

For cloud, use `/root/gems-pos` as the final argument instead. The updater takes a backup first, updates the addon/schema and starts Odoo. It preserves existing shop data, accounts, permission settings, Compose, HTTPS, maintenance and scheduled backups. Refresh Ctrl+Shift+R.

If Gems POS is not installed at all, use the separate `gems-pos-v13-wsl-full.zip`, extract it to `/root`, run `cd /root/gems-pos-wsl-v13 && bash install.sh`. It is a fresh local test installation with admin/admin and user/user. Requires Docker Desktop WSL integration. Windows browser: http://localhost:8080/gems. Later start: `bash start.sh`. Do not run a fresh initializer against a live shop; use the update package above.

## Use

Admin → Reports & profit. Choose Year and Whole year or an individual Month. All period boundaries use Myanmar time (Asia/Yangon), including sales immediately around midnight. The yearly table shows twelve months and the year total; a month filter shows that month and its total. Money is MMK.

- Stock In/Out: quantities of actual recorded ledger movements, including product opening quantities, stock corrections, sale movements and cancellation returns. Hiding/deleting history does not change physical movement totals. Cancelled sales can still have stock movements because both the original dispatch and the return actually occurred. Sold units are shown separately for valid sales only.
- Sales: voucher total after discount, excluding cancelled vouchers. Discount is shown separately and is not deducted twice.
- Cost: product Cost price per unit is captured on each sale line at checkout. Admin enters Cost price on Add/Edit product; website staff and delegated managers cannot read/change cost. An explicit zero is a known zero cost; blank means unknown. Product cost edits affect future sales only.
- Gross profit = sales after discount minus recorded cost of goods sold.
- Operating expenses: Add expense for rent, salary, transport, etc., with date/description/amount. Void an incorrect expense to exclude it while preserving its audit record. Repeated save requests use a token and do not duplicate the expense. The UI shows the latest 60 expenses in the selected period; totals include all expenses.
- Net profit / loss = gross profit minus recorded operating expenses. This is an operational report using sale-time unit costs, not FIFO/weighted-average inventory valuation. Purchases are not entered again as operating expenses; cost of sold goods is already deducted. Stock corrections are not booked automatically as monetary expenses.
- Missing costs: pre-v13 sales and new sales without Cost price show units without cost. Gross/net profit is unavailable for affected periods; no assumed zero cost or historical backfill. Known cost subtotal and revenue remain visible. Existing vouchers are never rewritten based on today's product cost.

Export Excel downloads a real `.xlsx` containing the selected period total, monthly breakdown, monetary number formats and explanatory notes. It opens in Excel/LibreOffice without CSV import. Export PDF opens a landscape A4 report and the browser print dialog: choose Save as PDF. No new PDF/Excel package is needed inside Odoo; the existing Myanmar font is bundled.

Reports, both export endpoints and expense endpoints are protected on the server for full Gems Administrators only. Delegated Manager/Staff profiles have no report access even if they have all-staff transaction view. v12 per-user permissions, stock editing, transaction cancellation and bulk barcode features remain included. Backups include cost snapshots and expenses automatically.

## Validation

Run the Python checks and JavaScript checks in `tests/`. Offline tests cover Myanmar month/year boundaries, losses, missing cost, valid XLSX readback, Excel formats, report/export/expense admin guards, expense validation/idempotency, actual sale-time cost snapshots, cost edit authorization, report UI/escaping and existing permissions/stock/cancellation/barcode/scanner regressions. Python/XML/JS/shell syntax is checked. Full Odoo/Docker runtime and Windows PDF saving must be checked after installation.
