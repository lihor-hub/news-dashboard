import type { ReactNode } from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  Svg: React.ComponentType<React.ComponentProps<'svg'>>;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Find What Matters',
    Svg: require('@site/static/img/feature-getting-started.svg').default,
    description: (
      <>
        Centralize trusted technical sources, then use freshness, recommendations, and a
        personalized brief to filter the noise.
      </>
    ),
  },
  {
    title: 'Understand Why',
    Svg: require('@site/static/img/feature-feed.svg').default,
    description: (
      <>
        Inspect article takeaways, context, and perspectives, then ask cited follow-up questions
        grounded in your news corpus.
      </>
    ),
  },
  {
    title: 'Remember It',
    Svg: require('@site/static/img/logo.svg').default,
    description: (
      <>
        Save and organize useful material, create learning artifacts, and revisit it through search,
        reading history, and the knowledge graph.
      </>
    ),
  },
  {
    title: 'Own Your Data',
    Svg: require('@site/static/img/feature-self-host.svg').default,
    description: (
      <>
        Self-host with Docker Compose or Helm for control over your sources, reading data, and AI
        provider configuration.
      </>
    ),
  },
];

function Feature({ title, Svg, description }: FeatureItem) {
  return (
    <div className={clsx('col col--3')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} aria-hidden="true" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
