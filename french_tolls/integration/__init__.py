# -*- coding=utf-8 -*-
"""The recorded drive-flow suite: real routes, real booths, replayed Google.

Separate from `french_tolls.tests` on purpose. That suite is specified to run
with both routers stopped and nothing under `data/` mounted, which is what makes
it runnable on a bare checkout. This one cannot start without 30 GB of graph.
Keeping them in one place would force the union of their dependencies on both.
"""
