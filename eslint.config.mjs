import js from '@eslint/js';
import babelParser from '@babel/eslint-parser';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';

export default [
  {
    ignores: [
      'frontend/dist',
      'node_modules',
      'design/',
      'coverage',
      'frontend/src/components/ui/**',
      // Stale git worktrees — lint runs on the whole tree so exclude them explicitly
      '.claude/worktrees/**',
      '.worktrees/**',
      // Python virtual environment — contains playwright/patchright JS bundles
      '.venv/**',
    ],
  },
  {
    files: ['frontend/src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          presets: [['@babel/preset-typescript', { ignoreExtensions: true }]],
          plugins: ['@babel/plugin-syntax-jsx'],
        },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.flat.recommended.rules,
      ...reactRefresh.configs.vite.rules,
      ...prettier.rules,
      // typescript-eslint 8.63.0 crashes while loading against TypeScript 7.
      // Use Babel for TS syntax linting and rely on `npm run typecheck` for
      // type-aware validation until upstream publishes TS 7 support.
      'no-undef': 'off',
      'no-unused-vars': 'off',
      // The app uses the classic fetch-in-effect pattern throughout; migrating
      // to a data-fetching library is out of scope for lint adoption.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['vite.config.ts'],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          presets: [['@babel/preset-typescript', { ignoreExtensions: true }]],
        },
      },
    },
    rules: {
      ...js.configs.recommended.rules,
      ...prettier.rules,
      'no-undef': 'off',
      'no-unused-vars': 'off',
    },
  },
];
