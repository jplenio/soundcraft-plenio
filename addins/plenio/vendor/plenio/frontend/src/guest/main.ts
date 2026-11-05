/** The party guests' song form (built into plenio/player/guest_static, served by the guests' server below its token
 * as ``make/``; owner's request 2026-10-25). */
import { createApp } from 'vue'

import '../player/styles.css'
import GuestMaker from './GuestMaker.vue'

createApp(GuestMaker).mount('#app')
