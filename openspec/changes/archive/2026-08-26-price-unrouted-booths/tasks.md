## 1. Record the stated role

- [x] 1.1 Merge the stated roles into the role map `apply_charges` consults, as `inventory_types | ov.one_way`, and update the docstring of `role()`, which currently explains the merge in terms of journey-dependent roles only. Verify that Beaurepaire `1581498325` keeps `type: enter` and its prices `05050: 53.9` and `05052: 54.6`, and that `data/vinci_price.yaml` is otherwise unchanged.
- [x] 1.2 Record an entry for every booth in `ov.one_way`, under the stated type, whether or not any route covers it. Verify that `36967326` gets `type: exit` and `36967365` gets `type: enter`, each with no other key.
- [x] 1.3 Verify that step 8 now counts `36967365` among its sources and `36967326` among its targets, without any change to `build_vinci_direct_prices.py`.

## 2. Price a stated barrier

- [x] 2.1 Build the single-passage loop over the booths typed `passthrough` by the override file and absent from `done_pairs` as `(booth, booth)`: submit `client.rate([gare])`, feed the response through `attribute()` with a synthetic route `{"from": booth, "to": booth, "covers": [{"node_id": booth}]}`, and apply the charges. Verify the six booths record `06028` 1.2, `02001` 55.5, `02057` 2.3, and `04390` 1.1.
- [x] 2.2 Verify no single-passage request is issued for a booth typed `enter` or `exit`, and that `1581498325` gains no `price` key. Its lone-passage answer is 14.70, which is not what Beaurepaire charges, so a request that fetched it would be a bug.
- [x] 2.3 Stop and name the booth when a stated `passthrough` gets `No rate found.`. Verify by temporarily restating `36967365` as `passthrough` in a scratch copy of the override file, passed with `--overrides`; do not edit `data/osm_toll_booths_overrides.yaml`.
- [x] 2.4 Stop and name the booth when the response holds no item at all, distinct from an item carrying `No rate found.`.
- [x] 2.5 Record `(booth, booth)` in `done` only after the answer is applied in full, and write state as the route loop does. Verify that interrupting mid-request leaves that booth absent from `routes`.
- [x] 2.6 Verify the two booths of one gare agree: `1702349430` and `2193692586` both record 1.2, and the second changes nothing.

## 3. Close the accounting

- [x] 3.1 Add the end-of-run check that every booth in `ov.one_way` carries an entry in `data/vinci_price.yaml`, running on every invocation including one with nothing outstanding, and failing with the booth named. Verify by deleting one entry and re-running with everything else processed.
- [x] 3.2 Verify the "booth without a price is reported, not fatal" report does not name the two Perthus booths — no route covers them, so it never looked at them — and that its existing 20 rows are unchanged.

## 4. Let step 8 price the Perthus pairs

- [x] 4.1 Run `make build_vinci_direct_prices` with `--survey` and record how many clean Le Perthus pairs the operator declines to price. Roughly 65 pairs are expected to route clean.
- [x] 4.2 If the survey is empty, run without it and verify `36967365` gains a `prices` mapping and `36967326` stays `type` alone. If it is not empty, report the declined pairs and stop — deciding whether they are data faults or real absences is not this change's to make.

## 5. End to end

- [x] 5.1 Run `make build_vinci_prices` twice in succession and verify the second run issues no request and leaves `data/vinci_price.yaml` byte-identical.
- [x] 5.2 Verify `data/route_set.yaml`, `data/osm_toll_booths.yaml`, and `data/vinci_toll_booth.yaml` are unchanged by the whole change, and that step 7 still produces a byte-identical `data/bidirectional_booth_sides.yaml`.
