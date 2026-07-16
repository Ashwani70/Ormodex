// Flat ESLint config (ESLint 9+). The production build still lints through
// react-scripts/craco using the embedded eslintConfig in package.json; this
// file is what the editor's ESLint extension and any direct `eslint` v9 run
// use, so it mirrors the Create React App rule set plus the Aurora design
// guardrails. Optional plugins are loaded defensively so a missing dev
// dependency degrades gracefully instead of crashing the whole config.
const js = require("@eslint/js");
const globals = require("globals");
const react = require("eslint-plugin-react");
const reactHooks = require("eslint-plugin-react-hooks");

function tryRequire(name) {
  try {
    return require(name);
  } catch {
    return null;
  }
}

const jsxA11y = tryRequire("eslint-plugin-jsx-a11y");
const importPlugin = tryRequire("eslint-plugin-import");

// Aurora design-system guardrails (carried over from package.json eslintConfig).
const auroraNoRestrictedSyntax = [
  "warn",
  {
    selector:
      "JSXAttribute[name.name='style'] Property[key.name=/^(background|backgroundColor|color|borderColor)$/] > Literal[value=/#[0-9a-fA-F]{3,8}/]",
    message:
      "Aurora: don't hard-code hex colors in style props. Use a Tailwind token class (e.g. bg-primary, text-foreground) or a CSS var (var(--primary-color)).",
  },
  {
    selector:
      "JSXAttribute[name.name='style'] Property[key.name='boxShadow'] > Literal[value=/rgba?\\(|[0-9]+px/]",
    message:
      "Aurora: use a shadow token — style={{ boxShadow: 'var(--shadow-sm)' }} — not a custom shadow.",
  },
];

module.exports = [
  { ignores: ["build/**", "dist/**", "coverage/**", "node_modules/**", "public/**"] },
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2021,
      },
    },
    settings: { react: { version: "detect" } },
    plugins: {
      react,
      "react-hooks": reactHooks,
      ...(jsxA11y ? { "jsx-a11y": jsxA11y } : {}),
      ...(importPlugin ? { import: importPlugin } : {}),
    },
    rules: {
      ...react.configs.recommended.rules,
      ...(react.configs["jsx-runtime"]
        ? react.configs["jsx-runtime"].rules
        : {}),
      ...reactHooks.configs.recommended.rules,

      // CRA-equivalent leniency: the new JSX transform means React/PropTypes
      // imports and prop-types are not required, and unused vars are warnings.
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-react": "off",
      "react/prop-types": "off",
      "react/no-unescaped-entities": "off",
      "react/display-name": "off",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-empty": ["warn", { allowEmptyCatch: true }],

      // Design-system guardrails.
      "no-restricted-syntax": auroraNoRestrictedSyntax,
    },
  },
];
