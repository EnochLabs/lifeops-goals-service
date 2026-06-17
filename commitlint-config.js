module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",     // new feature
        "fix",      // bug fix
        "docs",     // documentation only
        "style",    // formatting, no logic change
        "refactor", // code change with no feature/fix
        "perf",     // performance improvement
        "test",     // adding or fixing tests
        "chore",    // tooling, dependencies, CI
        "revert",   // revert a previous commit
        "wip",      // work in progress (should not reach main)
      ],
    ],
    "scope-enum": [
      2,
      "always",
      [
        "goals",
        "phases",
        "actions",
        "momentum",
        "workers",
        "events",
        "auth",
        "middleware",
        "config",
        "models",
        "schemas",
        "repos",
        "services",
        "graphql",
        "ci",
        "deps",
        "docker",
      ],
    ],
    "subject-case": [2, "never", ["upper-case", "pascal-case", "start-case"]],
    "header-max-length": [2, "always", 100],
  },
};
