## MODIFIED Requirements

### Requirement: Configuration is read from the environment

The token, the API keys, the monthly ceiling on paid requests, the travel-time factor, the debug setting, the log level, the address route requests are sent to, and the public address of the site SHALL be read from the environment, each with a documented default where a default is meaningful.

Six entries this list carried are gone from it, and none of them was ever configured:

- **The published port** is fixed at 8080 because the front end proxies to it. A variable that changes it takes the site down rather than moving it.
- **The routers' addresses** are Compose service names on one network. The published host ports refuse connections, which this capability already requires nothing to use.
- **The fit threshold** is a measured value, chosen because the corpus leaves an empty band between 97.7% and 99.5%. `google-route-refinement` requires the evaluation and the drive flow to use the same one, and they already do — by reading the same constant, not the same variable.
- **The query budget** bounds how many local routing requests one journey's search may issue. It guards against a search that is looping, and a deployment that reaches it does not want a larger number, so it is a constant with its measurement beside it.
- **The reach** — how far an origin may be from a road — was a setting in one place and a literal in two others, and the bot's reply names a kilometre in prose. A value that three places have to agree on is one value, written once and read by all three.
- **The wage** belongs to `toll-weighted-graph`, which requires it to be settable there. It is a parameter of the pipeline that builds the weighted graph, and no service reads it from the environment.

The count of waypoints a link carries goes the same way: it is nine because a Google Maps URL carries nine, and a variable that raises it makes the search place points the link drops without saying so.

**They SHALL be declared in one place, and nothing else in the application package SHALL read the environment.** Each setting SHALL carry its name, its type, its default, and a sentence saying what it is for. A caller SHALL obtain a value by asking that one object, and SHALL receive it already of the type it is used at — a count as an integer, a distance as a number, a switch as a boolean.

The reason is not tidiness. `.env.example` is required below to document every setting, and while the settings were spread across nine modules the only way to enumerate them was to search the source for environment reads. Writing the list down for the first time found that **twelve of the twenty-one had never been configured in any environment** — container paths fixed by their mounts, a port fixed by what proxies to it, service names on a single network, two timeouts, a guard against a looping search, and values that were measured rather than chosen. A list that exists can be checked; prose about a list cannot.

**A value that several places must agree on SHALL be written once.** The reach is the example: the router enforced it, the bot compared against its own copy, and the reply text named it in prose. Two of the three ignored the setting entirely, so changing it moved one behaviour and left the other two contradicting it.

**A value nothing configures SHALL NOT be a setting.** Where every environment gives the same answer — because a container path is fixed by the mount, or a port by what proxies to it — the value SHALL be written where it is used, with a note saying who fixes it. An environment read that has never returned a value is worse than no read at all: it invites an operator to set it and to wonder why nothing moved, or why something broke.

**A value that cannot be read as its type SHALL fail at start-up rather than later.** A count or a factor set to something that is not a number SHALL stop the service, naming the value. `int` and `float` do this on their own; nothing SHALL wrap them to say it differently, because a layer of parsing exists only to reword an error that was already clear.

**An empty value SHALL count as unset.** Compose passes several of these as `${VAR:-}`, so a variable nobody set arrives as the empty string rather than absent, and a setting that read it directly would try to make a number of `""`.

A switch SHALL read the words an operator would write: `1`, `true`, `yes` and `on` are on, in any casing, and everything else is off. It SHALL NOT be on because its value was spelled in capitals, which is what `not in ("", "0", "false", "False")` did to `FALSE` and to `no`.

`URL` SHALL be required. The service SHALL fail to start, naming it, when it is unset or empty. It is the address the bot's comparison-map link is built from, and a bot that does not know it would write a link to nowhere. Starting anyway would mean sending a message whose only link is broken.

**Nothing in the declaration SHALL make a value mandatory.** A field holds what the environment gave it, or its default, and reading one never fails for want of another. That is what lets the unit suite import the routing client, the booth loader and the refinement with no environment at all, as it is specified to.

A service that cannot run without a value SHALL refuse to start, itself, naming the variable. It SHALL do so at its entry point rather than when some module it happens to import is loaded: `URL` used to stop the process from the body of a module, which is why a test could not import that module at all.

Every service that answers a route query SHALL receive it — the web application and the bot alike. The travel-time factor SHALL reach both for the same reason: a bot quoting one duration and the page another for the same journey is the same fault in a different key.

**Every service that asks Google SHALL receive the key and the monthly ceiling.** The bot did not need them while it wrote links that came back through the web application to be refined; it asks directly now, and a service missing them reads its ceiling as zero and tells every driver its link was never checked — which is indistinguishable, from outside, from a month whose budget really is spent.

The travel-time factor SHALL default to 1, which serves the router's own time unchanged.

The debug setting SHALL default to off. It causes paid requests on every page load, and a deployment that has not asked for that SHALL NOT get it.

The Google key and the monthly ceiling SHALL be optional. Without them the service answers every journey unrefined rather than failing to start. `.env.example` SHALL document every one.

A secret SHALL NOT be committed and SHALL NOT appear in a failure record or a log line.

#### Scenario: Every variable is documented

- **WHEN** `.env.example` is read
- **THEN** it names every setting the application reads

#### Scenario: The reach is one value

- **WHEN** a location further from the road than the reach is sent
- **THEN** the router's limit, the check that rejects it, and the words the driver reads all come from one constant

#### Scenario: A knob that turns nothing is not offered

- **WHEN** a value is the same in every environment the application runs in
- **THEN** it is a constant where it is used, and no environment variable names it

#### Scenario: The settings are declared in one place

- **WHEN** the application package is searched for environment reads
- **THEN** the only one is the module that declares the settings

#### Scenario: A setting arrives already typed

- **WHEN** a caller reads the monthly ceiling, the travel-time factor, and the debug setting
- **THEN** it receives an integer, a number, and a boolean, and does not convert anything

#### Scenario: A value that cannot be read stops the service

- **WHEN** a count or a factor is set to something that is not a number
- **THEN** start-up fails, naming the value, and no layer of parsing has reworded it

#### Scenario: An empty value is an unset one

- **WHEN** a variable is passed through as the empty string
- **THEN** the setting holds its default rather than trying to read `""` as a number

#### Scenario: A switch spelled in capitals is still off

- **WHEN** the debug setting is `FALSE`, `No`, `off`, or anything that is not one of the words for on
- **THEN** it is off

#### Scenario: Importing does not require configuring

- **WHEN** the routing client, the booth loader and the refinement are imported with an empty environment
- **THEN** every import succeeds, and each setting holds its default

#### Scenario: The debug setting is off unless asked for

- **WHEN** no debug setting is configured
- **THEN** the page draws no overlay and makes no Google request on load

#### Scenario: The travel-time factor defaults to serving the router's own time

- **WHEN** no factor is configured
- **THEN** `duration` equals `duration_osrm` on every route

#### Scenario: The service runs without a Google key

- **WHEN** no Google key is configured
- **THEN** the service starts and answers every journey with unrefined waypoints

#### Scenario: The service refuses to run without a public address

- **WHEN** `URL` is unset or empty
- **THEN** the service exits at start-up naming it, from its own entry point rather than from a module it imported

#### Scenario: The bot and the web application agree

- **WHEN** the same journey is answered by the bot and by the web application
- **THEN** both quote the same duration

#### Scenario: Every service that asks Google can

- **WHEN** a service that makes Google requests starts
- **THEN** it has the key and a monthly ceiling above zero where one is configured; the fit threshold travels with the code and cannot be missing

#### Scenario: A missing ceiling is not mistaken for a spent one

- **WHEN** a service configured with a Google key reports that a link was not checked
- **THEN** it is because the month's requests are actually spent, not because the ceiling never reached it
