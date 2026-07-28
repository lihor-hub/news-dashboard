---
title: Hosted or self-hosted?
sidebar_position: 1
---

# Hosted or self-hosted?

Choose an on-ramp based on who should operate the server. The reading workflow
is the same after you sign in, but account creation and server configuration
belong to different people.

| Option                                                                | Best for                                                                     | Who creates accounts?                                                                             | Who controls the server?                                               |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Official hosted service** at [news.lihor.ro](https://news.lihor.ro) | Reading without operating infrastructure                                     | A hosted-service administrator, configured email-code auto-registration, or Keycloak registration | The hosted-service deployment operator                                 |
| **Local demo**                                                        | Trying the interface with sample data                                        | Nobody; use the bundled read-only `guest` account                                                 | You run the temporary demo stack, but it needs no manual configuration |
| **Self-hosted deployment**                                            | Owning the infrastructure, data location, integrations, and release schedule | Your instance administrator                                                                       | You or your deployment operator                                        |

## Know which role you have

- A **reader** signs in, manages their sources and reading state, and chooses
  the personal settings exposed by the app.
- An **administrator** manages users and administrator-only app pages for one
  instance. With local password authentication, an administrator creates
  additional accounts.
- A **deployment operator** runs the server and controls environment-level
  choices such as authentication, AI providers, email, push notifications,
  storage, backups, and upgrades.

One person can hold all three roles on a small self-hosted instance. On the
official hosted service, a reader does not need deployment access.

## Use the official hosted service

Open [news.lihor.ro](https://news.lihor.ro) if you have an account for the
official service. Account creation depends on the authentication mode selected
by its operator:

- local password accounts are created by an administrator;
- email-code login creates an account for an unknown email when outbound email
  works and the deployment operator enables `OTP_AUTO_REGISTER` (enabled by
  default); and
- a **Create Account** link appears when Keycloak registration is enabled.

Email-code login remains available alongside Keycloak, so an instance can
offer both email auto-registration and Keycloak registration. Do not assume
either public path is available on a particular deployment; follow
[Create a web account](create-web-account.md) for the sign-in paths.

The hosted operator, not the reader, decides which optional server capabilities
are configured. Settings in the app can enable a capability for your account
only after the server supports it.

## Try the local demo

Use [Try the demo](try-the-demo.md) to start a throwaway local instance with
sample articles and a read-only guest account. It is useful for browsing Today,
searching, opening articles, and exploring the navigation without creating
sources or configuring AI keys.

The demo is not a permanent account or a public deployment. Its guest account
rejects changes such as starring, saving, adding sources, and editing settings.

## Run your own instance

Self-hosting gives your deployment operator control of PostgreSQL, account
bootstrap, authentication, optional AI and delivery providers, persistent
storage, backups, and upgrades. It also makes that operator responsible for
secrets, availability, and maintenance.

Start with the repository
[Quick Start](https://github.com/lihor-hub/news-dashboard#quick-start), then use
the [Self-Hosting guide](/docs/self-hosting) for production configuration and
operations.

## Start reading

After signing in, take the [application tour](../user-guide/application-tour.md),
then use [Today Feed and triage](../user-guide/today-feed-triage.md) for the
first complete reading workflow.
