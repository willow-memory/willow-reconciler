# Changelog

All notable changes to this project are documented here. The format follows
[Conventional Commits](https://www.conventionalcommits.org/) and this file is
maintained by [release-please](https://github.com/googleapis/release-please).

## [0.2.0](https://github.com/willow-memory/willow-reconciler/compare/v0.1.0...v0.2.0) (2026-09-11)


### Added

* close the write-side loop for the Idea-Id convention ([717c877](https://github.com/willow-memory/willow-reconciler/commit/717c87786a13df54053ef1c2d13d088517059e74))
* close the write-side loop for the Idea-Id convention ([d01cdb0](https://github.com/willow-memory/willow-reconciler/commit/d01cdb0af18c1032d83d4e9e0a9a270674bfd140))


### Fixed

* anchor legend-tag regexes so a mid-prose marker is not a tag ([9c8be17](https://github.com/willow-memory/willow-reconciler/commit/9c8be17416898ebc6c7ff80811e9a127ccd47736))
* close two false-LANDED paths found by adversarial audit ([46d18bd](https://github.com/willow-memory/willow-reconciler/commit/46d18bd5bbc9b4065ddf11a005cddb8df59f66b5))

## 0.1.0 (2026-09-11)


### Added

* Initial Slice 0 idea-to-landing reconciler: reads a fleet doc's numbered
  items and the target repo's own git history, then reports — deterministically
  and stdlib-only, with no model call — how many proposed ideas have landed,
  partially landed, or show no evidence of having started.
* An honest, non-circular hold-out acceptance test (`reconciler validate`
  wiring in `validate.py`): the legend tag is stripped from each hand-tagged
  item before reclassification, so the score measures what the tool can
  actually recover rather than echoing a tag it just read.
* The `Idea-Id` commit-trailer convention (see `CONVENTION.md`) that gives the
  reconciler a durable join key going forward.
