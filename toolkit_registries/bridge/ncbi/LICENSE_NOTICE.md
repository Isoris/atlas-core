# NCBI E-utils — attribution

The NCBI Entrez Programming Utilities (E-utils) are operated by the
National Center for Biotechnology Information at the U.S. National
Library of Medicine.

- Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25497/
- Disclaimer + policies: https://www.ncbi.nlm.nih.gov/home/about/policies/

NCBI data are public domain unless otherwise stated by individual
submitting institutions.

## Rate limits

Without an NCBI API key: **3 requests per second** ceiling, enforced
globally per IP.  With an API key: **10 requests per second**.

To use an API key, set the `api_key` query param on any endpoint call.
Get a key at https://account.ncbi.nlm.nih.gov/.

atlas-core's bridge_client honours the 350 ms `min_interval_ms` by
default; bump down to 100 ms once you've configured an API key.

## Atlas-core compliance

- no re-hosting; per-endpoint cache TTL (1 hr search, 1 wk summary,
  30 days full fetch)
- 3 concurrent connections cap (NCBI's recommended ceiling)
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
