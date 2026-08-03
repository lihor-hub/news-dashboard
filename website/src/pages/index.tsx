import type { ReactNode } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HeroArt() {
  // Newspaper-layout motif, echoing the app icon.
  return (
    <svg
      className={styles.heroArt}
      viewBox="0 0 220 220"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden="true"
    >
      <rect width="220" height="220" rx="36" fill="#2e2a24" />
      <rect x="30" y="30" width="160" height="26" rx="9" fill="#f0ede8" />
      <rect x="30" y="74" width="74" height="12" rx="6" fill="#f0ede8" opacity="0.78" />
      <rect x="30" y="98" width="74" height="12" rx="6" fill="#f0ede8" opacity="0.6" />
      <rect x="30" y="122" width="60" height="12" rx="6" fill="#f0ede8" opacity="0.44" />
      <rect x="30" y="146" width="66" height="12" rx="6" fill="#f0ede8" opacity="0.28" />
      <rect x="120" y="74" width="70" height="70" rx="12" fill="#c8a45e" opacity="0.85" />
      <rect x="120" y="158" width="70" height="10" rx="5" fill="#f0ede8" opacity="0.35" />
    </svg>
  );
}

function ResearchWorkflow() {
  return (
    <section className={styles.screenshot}>
      <div className="container">
        <Heading as="h2" className={styles.workflowTitle}>
          From a crowded feed to knowledge you can use
        </Heading>
        <p className={styles.workflowIntro}>
          Centralize technical sources, let recommendations and a personalized brief surface what
          matters, inspect the context, ask cited follow-ups, and retain the useful parts.
        </p>
        <div className={styles.screenshotGrid}>
          <figure className={styles.screenshotFigure}>
            <img
              src="/img/briefing.webp"
              alt="Personalized AI briefing generated from deterministic demo articles"
              className={styles.screenshotImg}
              loading="lazy"
            />
            <figcaption>
              Start with a personalized brief of the technical news that matters.
            </figcaption>
          </figure>
          <figure className={styles.screenshotFigure}>
            <img
              src="/img/article-detail.webp"
              alt="Article reader with AI-generated takeaways, context, and perspectives from deterministic demo data"
              className={styles.screenshotImg}
              loading="lazy"
            />
            <figcaption>
              Understand an article through takeaways, context, and perspectives.
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  );
}

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={styles.heroBanner}>
      <div className={clsx('container', styles.heroInner)}>
        <div className={styles.heroText}>
          <Heading as="h1" className={styles.heroTitle}>
            {siteConfig.title}
          </Heading>
          <p className={styles.heroSubtitle}>
            Your AI research desk for technical news. Find what matters, understand why, and
            remember it.
          </p>
          <p className={styles.heroDetail}>
            Built for developers keeping up with fast-moving sources, personalized briefings,
            article intelligence, and cited follow-up answers.
          </p>
          <div className={styles.buttons}>
            <Link className="button button--primary button--lg" href="https://news.lihor.ro">
              Try the App
            </Link>
            <Link
              className={clsx('button button--outline button--lg', styles.buttonGhost)}
              href="https://github.com/lihor-hub/news-dashboard#quick-start"
            >
              Run It Yourself
            </Link>
          </div>
        </div>
        <HeroArt />
      </div>
    </header>
  );
}

const docSections = [
  {
    title: 'Getting Started',
    to: '/docs/getting-started',
    description: 'Try the hosted app, install Android, or choose a self-hosted setup.',
  },
  {
    title: 'User Guide',
    to: '/docs/user-guide',
    description: 'Find, understand, and retain technical news with briefings and AI tools.',
  },
  {
    title: 'Self-Hosting',
    to: '/docs/self-hosting',
    description: 'Deploy with Docker Compose or Helm and operate your instance.',
  },
  {
    title: 'Configuration',
    to: '/docs/configuration',
    description: 'Authentication, HTTPS with Caddy, and Postgres backups.',
  },
  {
    title: 'Architecture',
    to: '/docs/architecture',
    description: 'How the backend, frontend, and ingestion pipeline fit together.',
  },
  {
    title: 'Contributing',
    to: '/docs/contributing',
    description: 'Development setup, conventions, and how changes ship.',
  },
];

function DocSections() {
  return (
    <section className={styles.sections}>
      <div className="container">
        <Heading as="h2" className={styles.sectionsTitle}>
          Explore the docs
        </Heading>
        <div className={styles.sectionsGrid}>
          {docSections.map((section) => (
            <Link key={section.to} to={section.to} className={styles.sectionCard}>
              <Heading as="h3">{section.title}</Heading>
              <p>{section.description}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="News Dashboard is your AI research desk for technical news: find what matters, understand why, and remember it."
    >
      <HomepageHeader />
      <ResearchWorkflow />
      <main>
        <HomepageFeatures />
        <DocSections />
      </main>
    </Layout>
  );
}
