# Feature Request

The gateway introduced a new way to handle the authentication token for the header. We need to update all the packages that use this header to use the new name. Check this PR that introduce the change: https://github.com/mozilla-ai/gateway/pull/45 No need for backward compatibility.