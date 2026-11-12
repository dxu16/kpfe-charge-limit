# Armada contribution review

Checked 2026-11-10 against [armada-os/armada](https://github.com/armada-os/armada) at `066ecdc0d26edf7ba228cec26cbd2054810e92f8`.

No `CONTRIBUTING` file, `AGENTS.md`, or pull-request template was found in the recursive repository tree. The organization-wide `.github` repository lookup returned HTTP 404; the documentation repository's current tree had no contribution/development guide path. This is a scoped finding, not a claim that maintainers cannot impose additional review requirements. Do not confuse this project with the unrelated Kubernetes `armadaproject/armada`, whose DCO policy is not evidence of this project's policy.

The applicable published instructions and conventions are:

| Source | Requirement or convention | This preparation |
| --- | --- | --- |
| [README / Development](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/README.md#development) | Issues and PRs welcome; `just check`; just/Podman development environment | Prepared local RFC diff and PR text; full checks remain pending |
| [packages/README.md](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/packages/README.md) | Pinned upstream + patches + build script; record provenance in PATCHES.md | Added 0905 patch and provenance entry |
| [kernel build script](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/packages/kernel/scripts/build-kernel.sh) | Explicit `patches/series`; preflight every patch hunk | Inserted after 0904; checked full application and source identity |
| [package-hash.sh](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/packages/package-hash.sh) | Hashes package contents for build identity | No gratuitous VERSION bump or image/config edits |
| [LICENSE.md](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/LICENSE.md) | Bundled modifications keep upstream license | Linux GPL-2.0-only source retained |

`Justfile` defines `just check` as the shell test suite plus Just recipe formatting checks. Those checks and the complete `just package kernel` build have **not** been run in this packaging session: this Windows workspace lacks the project's Linux build environment. Prior exact-runtime-config module build and focused tests are recorded separately; they are not a substitute for the full project checks.

The commit title follows existing `fix(kernel): ...` usage observed in this repository; no mandatory title grammar or DCO requirement was found. Git user.name/user.email were not configured in this workspace. The output is an applicable unified diff, not an attributed/signed email commit. Before submission, the contributor should make their own commit with their chosen identity and any sign-off required by maintainers. The base charge-limit patch was originally submitted in [Armada PR #881](https://github.com/armada-os/armada/pull/881).
