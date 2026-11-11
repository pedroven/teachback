# Changelog

Notable changes to teachback. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Storage for reviews: concepts you haven't fixed yet live in `~/.teachback/concepts.json` (`TEACHBACK_HOME` overrides the folder) and are scheduled with FSRS. Nothing in the CLI uses it yet.

## [0.0.3] - 2026-11-10

### Added

- Pairing mode skill (`/teachback`). Install it by copying `skills/teachback` into your agent's skills folder.

### Changed

- Renamed from aprendiz to teachback: the PyPI package, the CLI, the Python package and the skill.

## [0.0.2] - 2026-11-10

### Added

- MIT license and repository link in the PyPI metadata. Published as aprendiz.

## [0.0.1] - 2026-11-10

### Added

- Placeholder package that claims the name on PyPI. Published as aprendiz.
