# Changelog

## [0.2.2](https://github.com/homestead-affairs/homestead-health/compare/v0.2.1...v0.2.2) (2026-09-11)


### Fixed

* read the living log through the engine's reader so a sealed log refuses instead of answering "never replaced" ([67dc237](https://github.com/homestead-affairs/homestead-health/commit/67dc2376272a1afbf6aa8ead393720c3e1f44b8d))
* read the living log through the engine's reader so a sealed log refuses instead of answering "never replaced" ([#23](https://github.com/homestead-affairs/homestead-health/issues/23)) ([73126ba](https://github.com/homestead-affairs/homestead-health/commit/73126ba7ec702552007e620f6fbbfdcfdb855743))
* refuse by name on every unreadable living ledger, not only the sealed one ([011eae9](https://github.com/homestead-affairs/homestead-health/commit/011eae9403ca73990a813b0654886ee6d669049b))


### Build

* **deps:** floor homestead-affairs at 0.11.0 ([be87324](https://github.com/homestead-affairs/homestead-health/commit/be8732411f67310766329718ee58f2a47832017b))

## [0.2.1](https://github.com/homestead-affairs/homestead-health/compare/v0.2.0...v0.2.1) (2026-09-11)


### Fixed

* drain a refused request body before the socket closes ([a46a4c8](https://github.com/homestead-affairs/homestead-health/commit/a46a4c87147b88d92181b1a49b1d150f39e6dae6))


### Build

* **deps:** widen the engine cap to <1.0 and pay the RECORD_ADDED debt ([5649afe](https://github.com/homestead-affairs/homestead-health/commit/5649afe49f7ae522fa3e985abc3efb48fb21162a))

## [0.2.0](https://github.com/homestead-affairs/homestead-health/compare/v0.1.0...v0.2.0) (2026-09-11)


### Added

* dose records a household enters itself, by subject ([589622b](https://github.com/homestead-affairs/homestead-health/commit/589622b9ebbebacfc22b018a83a73edca1271433))


### Fixed

* answer every refusal instead of dropping the connection ([15bea37](https://github.com/homestead-affairs/homestead-health/commit/15bea371b30a9e21dbeffcca545de3ea150e7b53))

## [0.1.0](https://github.com/rudi193-cmd/homestead-health/compare/v0.0.1...v0.1.0) (2026-08-18)


### Added

* extract homestead-health into its own repo (promotion from safe-app-store) ([9c94174](https://github.com/rudi193-cmd/homestead-health/commit/9c941746ce1f2e1702fb2e4fa9018e364f1db00b))

## Changelog

All notable changes to this project are documented in this file. It is
maintained by release-please from the conventional-commit history — see
`release-please-config.json`. The first standing release (`v0.1.0`) is the
promotion of this module out of the safe-app-store playground into its own
repo; release-please cuts it from the commits, with `0.0.1` (what the code
called itself while it incubated) as the baseline it compares from.
