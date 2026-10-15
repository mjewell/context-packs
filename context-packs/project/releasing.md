---
when: Releasing a new version to npm
---
# Releasing

`package.json` and `.claude-plugin/plugin.json` carry the same version: npm reads the first and Claude Code the second, so bump both in one commit. While the version is below 1.0, bump the minor version for a breaking change and the patch version otherwise.

```bash
python3 -m unittest discover tests
npm version patch --no-git-tag-version   # minor for a breaking change
# set "version" in .claude-plugin/plugin.json to match
git commit -am <version>
git tag -a v<version> -m <version>
npm publish                               # asks for 2FA in the browser
git push origin main --follow-tags
```

npm can take a minute or two to serve a new version after `npm publish` succeeds.
