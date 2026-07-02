import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'News Dashboard',
  tagline: 'Your private, self-hosted news platform',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Served at a dedicated custom domain, so baseUrl is root.
  url: 'https://docs.lihor.ro',
  baseUrl: '/',

  // GitHub pages deployment config.
  organizationName: 'lihor-hub',
  projectName: 'news-dashboard',

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/lihor-hub/news-dashboard/tree/main/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themes: ['@easyops-cn/docusaurus-search-local'],

  themeConfig: {
    image: 'img/social-card.png',
    metadata: [
      {
        name: 'description',
        content: 'Documentation for News Dashboard — your private, self-hosted news platform.',
      },
    ],
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'News Dashboard',
      logo: {
        alt: 'News Dashboard Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://news.lihor.ro',
          label: 'Open the App',
          position: 'right',
        },
        {
          href: 'https://github.com/lihor-hub/news-dashboard',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/getting-started',
            },
            {
              label: 'Self-Hosting',
              to: '/docs/self-hosting',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub Discussions',
              href: 'https://github.com/lihor-hub/news-dashboard/discussions',
            },
            {
              label: 'Issues',
              href: 'https://github.com/lihor-hub/news-dashboard/issues',
            },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'News Dashboard App',
              href: 'https://news.lihor.ro',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/lihor-hub/news-dashboard',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Ioachim Lihor · News Dashboard`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
