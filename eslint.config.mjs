import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
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
    ],
  },
  {
    files: ['frontend/src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettier,
    ],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // The app uses the classic fetch-in-effect pattern throughout; migrating
      // to a data-fetching library is out of scope for lint adoption.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['vite.config.ts'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended, prettier],
  }
);
