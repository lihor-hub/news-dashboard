/**
 * Tests for #860 — rebrand the documentation website with the News Dashboard
 * identity instead of the stock Docusaurus template assets.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

const websiteDir = join(process.cwd(), 'website');
const imgDir = join(websiteDir, 'static', 'img');

describe('documentation website branding (#860)', () => {
  it('ships no Docusaurus template imagery', () => {
    const templateAssets = readdirSync(imgDir).filter((name) => /docusaurus|undraw/i.test(name));
    expect(templateAssets).toEqual([]);
  });

  it('uses the News Dashboard mark as the navbar logo, not the dinosaur', () => {
    const logo = readFileSync(join(imgDir, 'logo.svg'), 'utf8');
    // Template dinosaur is drawn in Docusaurus green; the brand mark uses the
    // app's warm charcoal + amber palette from public/favicon.svg.
    expect(logo).not.toContain('#3ECC5F');
    expect(logo.toLowerCase()).toContain('#c8a45e');
  });

  it('references an existing brand social card from the site config', () => {
    const config = readFileSync(join(websiteDir, 'docusaurus.config.ts'), 'utf8');
    expect(config).not.toContain('docusaurus-social-card');
    const image = /image:\s*'([^']+)'/.exec(config)?.[1];
    expect(image).toBeTruthy();
    expect(existsSync(join(websiteDir, 'static', image!))).toBe(true);
  });

  it('renders homepage features with brand illustrations, not undraw art', () => {
    const features = readFileSync(
      join(websiteDir, 'src', 'components', 'HomepageFeatures', 'index.tsx'),
      'utf8'
    );
    expect(features).not.toContain('undraw');
    const referenced = [...features.matchAll(/static\/img\/([\w.-]+\.svg)/g)].map((m) => m[1]);
    expect(referenced.length).toBeGreaterThan(0);
    for (const file of referenced) {
      expect(existsSync(join(imgDir, file))).toBe(true);
    }
  });
});
