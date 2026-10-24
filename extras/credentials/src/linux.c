/* SPDX-License-Identifier: MIT */
/* Freedesktop Secret Service through libsecret. Items live in the default
   collection under the schema "org.exreader.Credentials" with exact
   (namespace, account) attributes. The module never unlocks or prompts: an
   absent service, absent default collection or locked item is UNAVAILABLE. */
#include "backend.h"
#include <libsecret/secret.h>
#include <string.h>

static const SecretSchema schema = {
  "org.exreader.Credentials", SECRET_SCHEMA_NONE,
  { { "namespace", SECRET_SCHEMA_ATTRIBUTE_STRING },
    { "account", SECRET_SCHEMA_ATTRIBUTE_STRING },
    { NULL, 0 } },
  0, 0, 0, 0, 0, 0, 0, 0
};

static exr_credentials_status map_error(GError *error) {
  exr_credentials_status status = EXR_CRED_IO;
  if (!error) return status;
  if (error->domain == G_DBUS_ERROR || error->domain == G_IO_ERROR ||
      (error->domain == SECRET_ERROR && (error->code == SECRET_ERROR_IS_LOCKED ||
                                         error->code == SECRET_ERROR_NO_SUCH_OBJECT)))
    status = EXR_CRED_UNAVAILABLE;
  g_error_free(error);
  return status;
}

static GHashTable *attributes(const char *ns, const char *account) {
  GHashTable *table = g_hash_table_new(g_str_hash, g_str_equal);
  g_hash_table_insert(table, (gpointer) "namespace", (gpointer)ns);
  g_hash_table_insert(table, (gpointer) "account", (gpointer)account);
  return table;
}

/* Connects without prompting and requires an unlocked default collection. */
static exr_credentials_status open_default(SecretService **out_service) {
  GError *error = NULL;
  SecretService *service = secret_service_get_sync(SECRET_SERVICE_OPEN_SESSION, NULL, &error);
  SecretCollection *collection;
  int locked;
  *out_service = NULL;
  if (!service) return error ? map_error(error) : EXR_CRED_UNAVAILABLE;
  collection = secret_collection_for_alias_sync(service, SECRET_COLLECTION_DEFAULT,
                                                SECRET_COLLECTION_NONE, NULL, &error);
  if (!collection) {
    g_object_unref(service);
    if (error) g_error_free(error);
    return EXR_CRED_UNAVAILABLE;
  }
  locked = secret_collection_get_locked(collection);
  g_object_unref(collection);
  if (locked) {
    g_object_unref(service);
    return EXR_CRED_UNAVAILABLE;
  }
  *out_service = service;
  return EXR_CRED_OK;
}

exr_credentials_status exr_cred_backend_put(const char *ns, const char *account,
                                            const uint8_t *secret, size_t secret_length) {
  SecretService *service;
  SecretValue *value;
  GHashTable *table;
  GError *error = NULL;
  char label[64 + EXR_CREDENTIALS_NAMESPACE_MAX];
  gboolean stored;
  exr_credentials_status status = open_default(&service);
  if (status != EXR_CRED_OK) return status;
  g_snprintf(label, sizeof label, "EXReader credential (%s)", ns);
  /* SecretValue keeps its own copy in non-pageable memory where available. */
  value = secret_value_new((const gchar *)secret, (gssize)secret_length, "application/octet-stream");
  table = attributes(ns, account);
  /* Replaces an item with identical schema attributes in the collection. */
  stored = secret_service_store_sync(service, &schema, table, SECRET_COLLECTION_DEFAULT,
                                     label, value, NULL, &error);
  g_hash_table_unref(table);
  secret_value_unref(value);
  g_object_unref(service);
  return stored ? EXR_CRED_OK : map_error(error);
}

exr_credentials_status exr_cred_backend_get(const char *ns, const char *account,
                                            uint8_t *buffer, size_t capacity, size_t *out_length) {
  SecretService *service;
  GHashTable *table;
  GError *error = NULL;
  GList *items, *node;
  exr_credentials_status status = open_default(&service);
  if (status != EXR_CRED_OK) return status;
  table = attributes(ns, account);
  /* No SECRET_SEARCH_UNLOCK: locked items are reported, never prompted for. */
  items = secret_service_search_sync(service, &schema, table, SECRET_SEARCH_LOAD_SECRETS,
                                     NULL, &error);
  g_hash_table_unref(table);
  if (error) {
    g_object_unref(service);
    return map_error(error);
  }
  status = EXR_CRED_NOT_FOUND;
  if (items) {
    SecretItem *item = (SecretItem *)items->data;
    SecretValue *value = secret_item_get_locked(item) ? NULL : secret_item_get_secret(item);
    if (!value) {
      status = EXR_CRED_UNAVAILABLE;
    } else {
      gsize length = 0;
      const gchar *bytes = secret_value_get(value, &length);
      status = exr_cred_copy_out(bytes, length, buffer, capacity, out_length);
      secret_value_unref(value);
    }
  }
  for (node = items; node; node = node->next) g_object_unref(node->data);
  g_list_free(items);
  g_object_unref(service);
  return status;
}

exr_credentials_status exr_cred_backend_delete(const char *ns, const char *account) {
  SecretService *service;
  GHashTable *table;
  GError *error = NULL;
  gboolean removed;
  exr_credentials_status status = open_default(&service);
  if (status != EXR_CRED_OK) return status;
  table = attributes(ns, account);
  removed = secret_service_clear_sync(service, &schema, table, NULL, &error);
  g_hash_table_unref(table);
  g_object_unref(service);
  if (removed) return EXR_CRED_OK;
  return error ? map_error(error) : EXR_CRED_NOT_FOUND;
}
