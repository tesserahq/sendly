<p align="center">
  <img width="140px" src="assets/logo.png">
  
  <p align="center">
    Sendly is envisioned as a unified email-sending service. It acts as an abstraction layer over multiple email providers (e.g. Postmark, SendGrid, Resend), providing a consistent API for other services to send emails and track their delivery status.
  </p>
</p>

## Features

* Provider-Agnostic API: A single /send endpoint (or similar) that clients call to send emails, without worrying about the underlying provider.

* Easily Switchable Providers: The ability to change the email provider via configuration (system setting or per-tenant setting) without code changes. This implies a pluggable provider architecture ￼ ￼.

* Email Status Tracking: Persist all email delivery events/statuses (sent, delivered, opened, bounced, etc.) in the database, regardless of provider ￼. This allows querying email status and history from Sendly’s database instead of calling provider APIs repeatedly.

* Webhook for Status Updates: Expose webhook endpoints that email providers call to report events (delivery, bounce, open, etc.). These webhooks will update the stored email status information.

* Multi-Tenancy: Support multiple tenants (clients) using the service. Each tenant can have its own email provider (and credentials) configured. The service should isolate data by tenant and use the correct provider per tenant.

* Performance and Scalability: Use Redis for queuing or caching to handle high volume email sending without blocking API calls. For example, emails can be enqueued and sent by background workers to improve throughput and responsiveness.

## Repobeats
![Alt](https://repobeats.axiom.co/api/embed/5b1e6fac4a6e12b6cfaac1aad31ada385f55879b.svg "Repobeats analytics image")
