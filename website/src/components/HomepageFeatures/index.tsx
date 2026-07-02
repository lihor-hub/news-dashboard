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
    title: 'Read Anywhere',
    Svg: require('@site/static/img/feature-getting-started.svg').default,
    description: (
      <>
        Install the Android app or sign in from any browser. Your feed, saved articles, and
        briefings stay in sync.
      </>
    ),
  },
  {
    title: 'Your Own Feed',
    Svg: require('@site/static/img/feature-feed.svg').default,
    description: (
      <>
        Curate sources, triage the Today Feed, and search across everything you have read — no
        algorithm deciding for you.
      </>
    ),
  },
  {
    title: 'Self-Hostable',
    Svg: require('@site/static/img/feature-self-host.svg').default,
    description: (
      <>
        Run News Dashboard on your own infrastructure with Docker Compose or Helm, with full control
        over your data.
      </>
    ),
  },
];

function Feature({ title, Svg, description }: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
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
