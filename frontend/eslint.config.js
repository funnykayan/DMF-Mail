const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  // Node.js server files
  {
    files: ["server.js", "ecosystem.config.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-console": "off",
      "no-unused-vars": "warn",
    },
  },

  // app.js – defines the DMFMail global
  {
    files: ["public/js/app.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-console": "off",
      "no-unused-vars": "warn",
    },
  },

  // Other browser-side JS – consumes the DMFMail global
  {
    files: ["public/js/admin.js", "public/js/webmail.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        DMFMail: "readonly",
      },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-console": "off",
      "no-unused-vars": "warn",
    },
  },
];
