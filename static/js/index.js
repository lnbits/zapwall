const DEFAULT_RELAYS = [
  'wss://relay.damus.io',
  'wss://relay.primal.net',
  'wss://nos.lol',
  'wss://relay.nostr.band',
  'wss://offchain.pub'
]

function defaultStats() {
  return {
    items: 0,
    sales_count: 0,
    sats_earned: 0,
    recent_unlocks: []
  }
}

function defaultSettings() {
  return {
    creator_nostr_pubkey: '',
    relay_urls: [...DEFAULT_RELAYS],
    bot_relay_urls: [...DEFAULT_RELAYS],
    dm_mode: 'nostrclient',
    signing_mode: 'external',
    signer_private_key: '',
    bot_private_key: '',
    sats_per_mb: 0,
    display_name: '',
    profile: {}
  }
}

function defaultItem() {
  return {
    title: '',
    slug: '',
    kind: 'text',
    preview_text: '',
    full_text: '',
    price: 100,
    cover_image: '',
    preview_media_urls: [],
    media_urls: [],
    media_upload_bytes: 0,
    unlock_type: 'dm_link',
    exact_amount_only: false,
    auto_dm_unlock: true,
    expires_at: null,
    status: 'draft'
  }
}

function normalizeSettings(settings) {
  if (!settings) return defaultSettings()
  return {
    ...defaultSettings(),
    ...settings,
    relay_urls: (settings.relay_urls_json
      ? JSON.parse(settings.relay_urls_json)
      : settings.relay_urls || []
    ).length
      ? settings.relay_urls_json
        ? JSON.parse(settings.relay_urls_json)
        : settings.relay_urls || []
      : [...DEFAULT_RELAYS],
    bot_relay_urls: (settings.bot_relay_urls_json
      ? JSON.parse(settings.bot_relay_urls_json)
      : settings.bot_relay_urls || []
    ).length
      ? settings.bot_relay_urls_json
        ? JSON.parse(settings.bot_relay_urls_json)
        : settings.bot_relay_urls || []
      : [...DEFAULT_RELAYS]
  }
}

window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data() {
    const seed = window.zapwallData || {}
    return {
      page: seed.page || 'settings',
      wallet: seed.wallet || null,
      isSuperUser: !!seed.isSuperUser,
      nostrclientActive: !!seed.nostrclientActive,
      stats: seed.stats || defaultStats(),
      settings: normalizeSettings(seed.settings),
      items: seed.items || [],
      buyers: seed.buyers || [],
      currentItem: seed.item ? {...defaultItem(), ...seed.item} : defaultItem(),
      currentStep: seed.item ? 2 : 1,
      itemAdvancedOpen: false,
      settingsAdvancedOpen: false,
      newPreviewMediaUrl: '',
      newMediaUrl: '',
      publishContentOverride: '',
      previewEvent: null,
      loading: false
    }
  },
  computed: {
    adminKey() {
      return this.wallet?.adminkey
    },
    invoiceKey() {
      return this.wallet?.inkey
    },
    publicLink() {
      return this.currentItem?.id
        ? `${window.location.origin}/zapwall/i/${this.currentItem.id}`
        : ''
    },
    unlockModeOptions() {
      return [
        {label: 'DM unlock link', value: 'dm_link'},
        {label: 'DM full content', value: 'dm_content'},
        {label: 'Receipt only', value: 'entitlement_only'}
      ]
    },
    itemKindOptions() {
      return [
        {label: 'Paid post', value: 'text'},
        {label: 'Image', value: 'image'},
        {label: 'File', value: 'file'},
        {label: 'Paid DM', value: 'dm'},
        {label: 'Subscription', value: 'subscription'}
      ]
    },
    itemStatusOptions() {
      return [
        {label: 'Draft', value: 'draft'},
        {label: 'Published', value: 'published'},
        {label: 'Archived', value: 'archived'}
      ]
    },
    settingsReady() {
      return !!this.settings.creator_nostr_pubkey
    },
    nostrDependencyText() {
      return this.nostrclientActive
        ? 'nostrclient is active. Relay listening and DM sending can use it.'
        : 'Install and enable the nostrclient extension. Zapwall depends on it for relay listening, preview publishing, and DM unlocks.'
    },
    hasItems() {
      return this.items.length > 0
    },
    canPublishCurrentItem() {
      return !!(
        this.currentItem.id &&
        this.currentItem.title &&
        this.currentItem.preview_text &&
        this.currentItem.price > 0
      )
    },
    currentItemTitle() {
      return this.currentItem?.id ? 'Edit Paywall' : 'Create Paywall'
    },
    currentItemStatusColor() {
      return this.statusColor(this.currentItem.status || 'draft')
    },
    setupChecklist() {
      return [
        {
          key: 'nostr',
          label: 'Connect your creator pubkey',
          done: this.settingsReady
        },
        {
          key: 'item',
          label: 'Create your first paywalled item',
          done: this.items.length > 0
        },
        {
          key: 'publish',
          label: 'Publish a preview note',
          done: this.items.some(item => !!item.preview_event_id)
        }
      ]
    }
  },
  methods: {
    goToPage(page) {
      this.page = page
    },
    startNewItem() {
      this.resetItem()
      this.currentStep = 1
      this.page = 'item'
    },
    shortPubkey(value) {
      if (!value) return ''
      if (value.length <= 18) return value
      return `${value.slice(0, 8)}...${value.slice(-8)}`
    },
    statusColor(status) {
      if (status === 'published') return 'positive'
      if (status === 'archived') return 'grey-7'
      return 'warning'
    },
    kindLabel(kind) {
      const option = this.itemKindOptions.find(option => option.value === kind)
      return option ? option.label : kind
    },
    openPublicItem(item) {
      window.open(`/zapwall/i/${item.id}`, '_blank', 'noopener')
    },
    async request(method, url, key, data) {
      const response = await LNbits.api.request(method, url, key, data)
      return response.data
    },
    async refreshDashboard() {
      this.stats = await this.request(
        'GET',
        '/zapwall/api/v1/dashboard',
        this.invoiceKey
      )
    },
    async refreshItems() {
      this.items = await this.request('GET', '/zapwall/api/v1/items', this.invoiceKey)
    },
    async refreshSettings() {
      const settings = await this.request(
        'GET',
        '/zapwall/api/v1/settings',
        this.adminKey
      )
      this.settings = normalizeSettings(settings)
    },
    async loadBuyers(itemId) {
      this.buyers = await this.request(
        'GET',
        `/zapwall/api/v1/items/${itemId}/buyers`,
        this.invoiceKey
      )
    },
    resetItem() {
      this.currentItem = defaultItem()
      this.previewEvent = null
      this.buyers = []
      this.newPreviewMediaUrl = ''
      this.newMediaUrl = ''
      this.publishContentOverride = ''
      this.itemAdvancedOpen = false
    },
    editItem(item) {
      this.currentItem = {
        ...defaultItem(),
        ...item,
        preview_media_urls: item.preview_media_urls || [],
        media_urls: item.media_urls || []
      }
      this.currentStep = 2
      this.page = 'item'
      this.previewEvent = null
      if (item.id) {
        this.loadBuyers(item.id)
      }
    },
    addPreviewMediaUrl() {
      const url = this.newPreviewMediaUrl.trim()
      if (!url) return
      this.currentItem.preview_media_urls = [
        ...this.currentItem.preview_media_urls,
        url
      ]
      this.newPreviewMediaUrl = ''
    },
    removePreviewMediaUrl(index) {
      this.currentItem.preview_media_urls.splice(index, 1)
    },
    addMediaUrl() {
      const url = this.newMediaUrl.trim()
      if (!url) return
      this.currentItem.media_urls = [...this.currentItem.media_urls, url]
      this.newMediaUrl = ''
    },
    removeMediaUrl(index) {
      this.currentItem.media_urls.splice(index, 1)
    },
    async saveItem() {
      this.loading = true
      try {
        const payload = {
          title: this.currentItem.title,
          slug: this.currentItem.slug || null,
          kind: this.currentItem.kind,
          preview_text: this.currentItem.preview_text,
          full_text: this.currentItem.full_text,
          price: Number(this.currentItem.price),
          cover_image: this.currentItem.cover_image || null,
          preview_media_urls: this.currentItem.preview_media_urls,
          media_urls: this.currentItem.media_urls,
          media_upload_bytes: Number(this.currentItem.media_upload_bytes || 0),
          unlock_type: this.currentItem.unlock_type,
          exact_amount_only: !!this.currentItem.exact_amount_only,
          auto_dm_unlock: !!this.currentItem.auto_dm_unlock,
          expires_at: this.currentItem.expires_at
            ? Number(this.currentItem.expires_at)
            : null,
          status: this.currentItem.status
        }
        const method = this.currentItem.id ? 'PUT' : 'POST'
        const url = this.currentItem.id
          ? `/zapwall/api/v1/items/${this.currentItem.id}`
          : '/zapwall/api/v1/items'
        this.currentItem = await this.request(method, url, this.adminKey, payload)
        await this.refreshItems()
        await this.refreshDashboard()
        if (this.currentItem.id) {
          await this.loadBuyers(this.currentItem.id)
        }
        this.currentStep = 2
        this.$q.notify({type: 'positive', message: 'Paywall saved'})
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.loading = false
      }
    },
    async deleteItem(item) {
      this.$q
        .dialog({
          title: 'Delete paywall',
          message: `Delete "${item.title}"?`,
          cancel: true,
          persistent: true
        })
        .onOk(async () => {
          try {
            await this.request(
              'DELETE',
              `/zapwall/api/v1/items/${item.id}`,
              this.adminKey
            )
            if (this.currentItem?.id === item.id) {
              this.resetItem()
              this.currentStep = 1
            }
            await this.refreshItems()
            await this.refreshDashboard()
            this.page = 'items'
            this.$q.notify({type: 'positive', message: 'Paywall deleted'})
          } catch (err) {
            LNbits.utils.notifyApiError(err)
          }
        })
    },
    async publishPreview() {
      if (!this.canPublishCurrentItem) return
      this.loading = true
      try {
        const response = await this.request(
          'POST',
          `/zapwall/api/v1/items/${this.currentItem.id}/publish-preview`,
          this.adminKey,
          {content: this.publishContentOverride || null}
        )
        this.previewEvent = response
        this.currentItem.preview_event_id = response.event_id
        this.currentItem.status = 'published'
        await this.refreshItems()
        await this.refreshDashboard()
        this.$q.notify({
          type: response.published ? 'positive' : 'warning',
          message: response.published
            ? 'Preview published to relays'
            : 'Preview event generated. Sign and publish it externally.'
        })
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.loading = false
      }
    },
    async saveSettings() {
      this.loading = true
      try {
        const payload = {
          creator_nostr_pubkey: this.settings.creator_nostr_pubkey || null,
          relay_urls: this.settings.relay_urls,
          bot_relay_urls: this.settings.bot_relay_urls,
          dm_mode: this.settings.dm_mode,
          signing_mode: this.settings.signing_mode,
          sats_per_mb: this.isSuperUser
            ? Number(this.settings.sats_per_mb || 0)
            : undefined,
          display_name: this.settings.display_name || null,
          profile: this.settings.profile || {}
        }
        if (this.settings.signer_private_key) {
          payload.signer_private_key = this.settings.signer_private_key
        }
        if (this.settings.bot_private_key) {
          payload.bot_private_key = this.settings.bot_private_key
        }
        await this.request('PUT', '/zapwall/api/v1/settings', this.adminKey, payload)
        await this.refreshSettings()
        await this.refreshDashboard()
        this.$q.notify({type: 'positive', message: 'Settings saved'})
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.loading = false
      }
    }
  },
  async created() {
    if (this.adminKey && this.invoiceKey) {
      await Promise.all([
        this.refreshDashboard(),
        this.refreshItems(),
        this.refreshSettings()
      ])
      if (this.currentItem?.id) {
        await this.loadBuyers(this.currentItem.id)
      }
    }
  }
})
