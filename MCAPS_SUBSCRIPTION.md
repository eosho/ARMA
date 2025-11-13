# Requesting an Azure Subscription in the FDPO Tenant

This guide explains how to request an Azure subscription in the **fdpo.onmicrosoft.com** managed tenant. As a requester, you will receive ‘Owner’ access to the subscription, but no admin permissions within Azure Active Directory (AAD). If you need additional licenses for your FDPO subscription, refer to the [License activation for FDPO tenant subscriptions](https://mcapsservices.powerappsportals.com/support/LicenseActivationForFDPO/?ServiceId=f818c69c-ddfd-48c5-bd3f-77354bdccbe7).

***

## Prerequisites

*   **Eligibility:** Only employees in MCAPS may use this option (Make sure you report to Judson Althoff in the org hierarchy).
*   **Security Group Registration:** You must be registered in the *MCAPS Azure Managed Environment* security group. Register via the process at [Request permission to the Managed Environment](https://myaccess.microsoft.com/@microsoft.onmicrosoft.com#/access-packages/fda1c45d-f5e4-43ca-a020-d9ac08f7880d).

    >💡 *Note: Registration can take 24–48 hours. Check your junk folder for the acceptance email.*

***

## Step-by-Step Instructions

### 1. Access the Request Form

*   Go to [Request New Cloud Services](https://aka.ms/MCAPSNewAzureSub).
*   First-time users may need to sign in. Use Azure AD and your Microsoft credentials.

### 2. Fill Out the Request Form

*   **Title:** Enter a suitable title for your request. e.g., "Requesting an Azure subscription in the FDPO tenant".
*   **Subscription Purpose:** Select `Hybrid (Self-Learning/Demo)` from the drop-down.
*   **Subscription Type:** Choose either `External Subscription` or `Internal Subscription`.
*   **Tenant Licensing:** Select available licenses you want enabled for your tenant.
    *   Enterprise Premium P2
    *   M365 E5
    *   Office 365 GCC E5
    >💡 *Note: This is only available for External Subscription types.*

##### FDPO Tenant Includes (Licenses Available):

*   Enterprise Mobility + Security E5
*   Azure Information Protection Premium P1 & P2
*   Azure Rights Management
*   Microsoft 365 Audit Platform
*   Microsoft Azure Multi-Factor Authentication
*   Microsoft Defender for Cloud Apps & Identity
*   Microsoft Entra ID P1 & P2
*   Microsoft Intune Plan 1

*For additional licenses, use the [License Activation for FDPO - MCAPS Services](https://mcapsservices.powerappsportals.com/support/LicenseActivationForFDPO/?ServiceId=f818c69c-ddfd-48c5-bd3f-77354bdccbe7) form.*

### 3. Requestor and Owner Details

*   **Requestor:** Auto-populates with your name.
*   **Subscription Owner:** Enter the owner’s name (can be changed if requesting for someone else).
*   **Reporting Manager:** Auto-populates based on the Subscription Owner.

    >💡 *Note: Requests can be raised on behalf of another person in the same organization.*

### 4. Approval Workflow

*   After submitting, an approval email is sent to the Reporting Manager.
*   The manager must approve or reject the request in the ITSM tool.

### 5. Additional Form Fields

*   **Time Zone:** Select your time zone.
*   **Monthly Spend:** Default is $500. If you select another value, provide a justification.
    *   If you select "Other," provide a written justification in the "Justification for High Spend" field.
*   **Tenant Display Name:** Custom display name for your tenant. eg., "MyAIGarageTenant".
    >💡 *Note: This is only available for External Subscription types.*

There are some additional fields available when you request an external subscription type and tenant type. Please review those fields and work with your manager for approval.

### 6. Terms and Conditions

*   Click to read the Terms and Conditions.
*   Check the box to agree and click Accept.

### 7. Submit the Request

*   Validate all required fields.
*   Click **Submit**.
*   Note the Case Number for tracking your request.
*   The case will be assigned to a Service Engineer; expect an email update from ITSM.

***

## Post-Submission Steps

*   Once approved by your manager, you’ll receive a welcome email from `mcapsservicesprodsa@microsoft.com` with the subject: *You’ve been asked to accept Azure subscription ownership*.
*   Click the link in the email to accept ownership via the Azure Portal.

### Finalizing Ownership

*   After accepting, ensure you select the correct tenant in Azure Portal (use the switch directory option under your username if needed).
*   Go to **Azure Portal → Subscriptions** and clear existing filters, including the checkbox: *Show only subscriptions selected in the global subscriptions filter*.

***

## Troubleshooting & Additional Resources

*   For issues with registration or license activation, refer to the internal support links above.
*   If you do not receive expected emails, check your junk/spam folders.

***

## Contact

*   For further assistance, contact the ITSM team or email <mcapsservicesprodsa@microsoft.com>.

***
