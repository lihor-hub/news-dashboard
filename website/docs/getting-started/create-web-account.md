# Create a Web Account

News Dashboard supports two authentication methods depending on how the server
is configured:

- **Local password auth** — username and password stored in the app's database
- **Keycloak auth** — single sign-on through an external Keycloak provider

The registration flow differs for each. This guide covers both.

## Before you start

You need the URL of a running News Dashboard instance. The public instance is
at **[news.lihor.ro](https://news.lihor.ro)**. Self-hosters should use their
own domain.

Open the URL in any modern browser (Chrome, Firefox, Safari, Edge). You will
see the **Sign in** page.

## Local password auth (default)

When Keycloak is not enabled, the login page shows a **username** and
**password** form, plus a link to switch to email code login.

### First admin bootstrap

The very first account on a fresh server is created through the **bootstrap
mechanism**. The server administrator sets the environment variables
`BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` before starting the
app. On first startup, the app creates an admin user with those credentials.

Ask your server administrator for the bootstrap credentials if you should be
the first admin.

### Additional users

If you are an admin, you can create additional users through the **Admin
panel** (visible to admin users only). Go to **Settings → Admin → Users**
and click **Generate user**. This creates a local user account with a
generated username and password that you can share with the new user.

### Signing in

1. Enter your **Username** and **Password**.
2. Click **Sign in**.
3. On success, you are redirected to your Today Feed (or the page you were
   trying to reach).

If you do not have an account yet, ask an admin to create one for you.

### Email code login (alternative)

The login page also offers an **email code** option. Click **Use email code
instead**, enter your email address, and a 6-digit code will be sent to it.
Enter the code to sign in. This requires the server to have an email sending
channel configured.

## Keycloak auth

When Keycloak is enabled, the login page shows a **Sign in with Keycloak**
button and a **Create Account** link.

1. Click **Sign in with Keycloak** to be redirected to the Keycloak login
   page.
2. Enter your Keycloak credentials.
3. After successful authentication, you are redirected back to News Dashboard.

To create a new account through Keycloak:

1. Click the **Create Account** link on the login page.
2. You are redirected to the Keycloak registration form.
3. Fill in the required fields and submit.
4. After registration, you are redirected back to News Dashboard and
   automatically signed in.

> The **Create Account** link is only available when Keycloak is enabled.
> For local password auth, account creation is handled by an admin through
> the Admin panel.

## After signing in

Once you are signed in, you land on your **Today Feed** — the main triage
view. See the [User Guide](/docs/user-guide) to learn how to use it.

If this is your first time using News Dashboard, the app will have already
seeded a set of default news sources. Articles will start appearing after the
next ingest cycle (or you can trigger an ingest from the **Sources** page).

## Troubleshooting

| Problem | Likely cause | Solution |
|---------|-------------|----------|
| "Not authenticated" / redirected to login | Session expired | Sign in again |
| "Invalid username or password" | Wrong credentials | Check your username and password; contact an admin to reset |
| No "Create Account" link | Server uses local auth | Ask an admin to create an account for you |
| Keycloak login fails | Keycloak server unreachable or misconfigured | Contact your server administrator |
