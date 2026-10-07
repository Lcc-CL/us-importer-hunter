# D4a real prospect calibration sample

Copy `prospect-calibration-template.csv` and add **3 to 5 real US importer
companies obtained by the user**.

- Required: `company_name`, plus either `source_url` or `source_external_id`.
- Strongly recommended: `website`, because the production workflow performs
  official-website research and contact discovery.
- Optional: `address`, `region`, `product_description`, `import_evidence`.
- Do not add fictional companies, test fixtures, LinkedIn data, credentials or
  API keys.

The manual CSV adapter accepts both the legacy `external_id` heading and the
template's clearer `source_external_id` alias.
