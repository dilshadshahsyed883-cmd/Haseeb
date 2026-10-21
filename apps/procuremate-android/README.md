# ProcureMate Pakistan — Android Beta

Native Android (Java, minSdk26) sourcing companion for Pakistani procurement suppliers. This project is isolated under `apps/procuremate-android`; it does not deploy or change existing PC/VPS apps.

## What works in beta
- Local persistent BOQ items and supplier/quotation entries
- Import images with Google ML Kit OCR, scanned PDFs (up to 20 pages), text and CSV; user reviews ambiguous OCR
- Editable item specifications, units and categories; multi-category catalog
- Suppliers by city, type, public source URLs, contact fields, manual prices
- Browser supplier search without keys; optional Serper API key for live organic supplier result discovery with explicit source links (results are unverified leads, not confirmed suppliers)
- English/Urdu RFQ drafting, Copy and Share, CSV export
- Screenshot-derived **sample/demo** tender data

## Limitations
No independent verification of live phone numbers; supplier results require manual review, no automated messaging. PDF scans rely on ML Kit Latin OCR; Urdu OCR and advanced table segmentation not guaranteed. Excel XLSX import is not supported in v0.1; convert to CSV. No multi-user syncing, pricing API, PPRA automation or auto-submission. Data stays locally on the device unless user explicitly searches/shares/exports; Serper credentials live in local preferences. Do not use a personal key on a shared device.

## Build
GitHub Actions `build-procuremate-apk.yml` builds a debug-signed test APK. It is not Play Store production-signed. For local build use Java 17, Android SDK 35, Gradle 8.10+: `gradle :app:assembleDebug`. Install APK from Actions artifact ZIP.
