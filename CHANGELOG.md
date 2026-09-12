# Changelog

All notable changes to this project are documented here. The format follows
[Conventional Commits](https://www.conventionalcommits.org/) and this file is
maintained by [release-please](https://github.com/googleapis/release-please).

## [0.6.0](https://github.com/willow-memory/willow-reconciler/compare/v0.5.0...v0.6.0) (2026-09-12)


### Added

* **cli:** reconciler conventions --json, the fleet's rule set from one home ([649a894](https://github.com/willow-memory/willow-reconciler/commit/649a894381dc000258b060facc003ccd912f0b73))
* **cli:** reconciler conventions --json; pr-title guard; the meta-scan ([d534944](https://github.com/willow-memory/willow-reconciler/commit/d5349444211aec0606a333ef494c7d05646a5ddc))

## [0.5.0](https://github.com/willow-memory/willow-reconciler/compare/v0.4.0...v0.5.0) (2026-09-12)


### Added

* reconciler fleet — one table across many repos, and --repo that works from a PyPI install ([539a5d2](https://github.com/willow-memory/willow-reconciler/commit/539a5d2d9cf10a874199690ed9f6dd4f7ceedd77))
* reconciler fleet — one table across many repos, with the honest recall number ([c7e4433](https://github.com/willow-memory/willow-reconciler/commit/c7e44339a82abd06762fe2dae61c6492959255ff))


### Fixed

* --repo accepts a path, and a bare name resolves beside the caller's checkout, not the installed package ([0ec9144](https://github.com/willow-memory/willow-reconciler/commit/0ec9144fc7b8c3130fd4cea1b227e01d031e98ea))

## [0.4.0](https://github.com/willow-memory/willow-reconciler/compare/v0.3.0...v0.4.0) (2026-09-11)


### Added

* surface which rule fired on each verdict ([de8dee9](https://github.com/willow-memory/willow-reconciler/commit/de8dee978b73285998df635246f7213e705fdac6))


### Fixed

* **cli:** classify the --doc read failure instead of echoing the OSError ([663b3e7](https://github.com/willow-memory/willow-reconciler/commit/663b3e7e82d41ccd1d7f9753687839b54b8aac7e))
* never let git's raw stderr reach an emitted verdict ([eacfa6d](https://github.com/willow-memory/willow-reconciler/commit/eacfa6dcaeceadffa15af9f382348ca367a6a7b0))

## [0.3.0](https://github.com/willow-memory/willow-reconciler/compare/v0.2.0...v0.3.0) (2026-09-11)


### Added

* add reconciler benchmark, the honest recall number ([add64a9](https://github.com/willow-memory/willow-reconciler/commit/add64a93f4378dc64cdc6f47287d30355811ef15))
* add reconciler benchmark, the honest recall number ([12104dd](https://github.com/willow-memory/willow-reconciler/commit/12104dd81da0d1ebca937812ad281770d0ba67d4))

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
