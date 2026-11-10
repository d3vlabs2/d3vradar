# Maps for every job — Radar 2.6

Map & commute appears on Discover, Saved jobs and Applications cards and in every job detail view, regardless of source. Unknown/remote-only locations are not treated as an office. An optional office address can be saved through Edit job; multiple semicolon-separated listing locations can be selected. Broad listing locations are marked approximate.

Set **Profile → Commute start address or ZIP**, then Save profile. This value stays in the encrypted profile and is not added to resumes or cover letters. It is sent to Google when you explicitly open commute directions. If blank, the existing Home location is used as an approximate start. Nothing contacts Google just from rendering the cards.

Without a key, Show location and Directions from home produce ordinary Google Maps links. Google displays the route distance and travel time when you open the link. No numeric mileage is invented or scraped.

For a map and route distance/time inside Radar, enable Maps Embed API in a Google Cloud project and obtain a key. Restrict that key to **Maps Embed API** and the **Websites** referrer `https://radar.example.com/*`. This is a browser-visible key, not a server secret. Add to the existing ~/jobradar/.env:

```
GOOGLE_MAPS_EMBED_API_KEY=your_restricted_maps_embed_key
```

Then `cd ~/jobradar` and `sudo docker compose up -d --force-recreate`. Do not replace the rest of .env. Google Cloud setup requires an enabled billing account; check Google's current terms. The Brave Search key is separate.

Documentation:
- https://developers.google.com/maps/documentation/urls/get-started
- https://developers.google.com/maps/documentation/embed/embedding-map
- https://developers.google.com/maps/documentation/embed/get-api-key

Validation: 85 backend tests, 18 Maps assertions, 19 date/statistics assertions and 15 extension checks passed. Browser preview confirmed a hybrid Buffalo listing's Maps panel and a correctly encoded route from the synthetic Albany home location. Encrypted origin persistence and optional office addresses were tested. An active Maps Embed API key was unavailable, so actual in-frame Google rendering/distance requires verification after key configuration. No precise user home address was sent during testing. The homelab has not been changed by these tests.

In 2.8, Profile labels the default as **Home address for directions**. Commute dialogs
prefill it in **Starting address**, which can be overridden for one route without
changing the saved profile. If no street address is saved, the home location is used.
