---
when: Releasing a new version to npm
---
# Releasing

`package.json` and `.claude-plugin/plugin.json` carry the same version: npm reads the first and Claude Code the second, so bump both in one commit. While the version is below 1.0, bump the minor version for a breaking change and the patch version otherwise.

`main` is protected, so the version commit lands through a PR. Merge it with a merge commit, not a squash, so the tagged commit itself ends up on `main`.

```bash
python3 -m unittest discover tests
git checkout -b release-<version>
npm version patch --no-git-tag-version   # minor for a breaking change
# set "version" in .claude-plugin/plugin.json to match
git commit -am <version>
git tag -a v<version> -m <version>
npm publish                               # asks for 2FA in the browser
git push -u origin HEAD --follow-tags
gh pr create --title <version> --body <notes>
gh pr merge --merge --delete-branch
gh release create v<version> --title <version> --notes-file <notes>
```

The release notes list what's new and what changed, saying what to do about anything that breaks.

npm can take a minute or two to serve a new version after `npm publish` succeeds.
