<template>
  <v-app>
    <v-main>
      <v-container>
        <v-card class="mb-6">
          <v-card-item>
            <v-card-title class="text-headline-small">SmartScrape Dashboard</v-card-title>
            <v-card-subtitle>Updated 20 minutes ago</v-card-subtitle>
          </v-card-item>
        </v-card>

        <v-row class="mb-6">
          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-briefcase-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Jobs Scraped</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-text-box-search-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Characters Parsed</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card prepend-icon="mdi-clock-outline" append-icon="mdi-trending-up">
              <v-card-title class="text-title-small text-uppercase text-grey ">Total Runtime</v-card-title>
              <v-card-text class="text-title-large font-weight-bold">{{ totalJobsScraped }}</v-card-text>
              <v-card-text class="text-green font-weight-medium pt-0">{{ totalJobsScrapedComparison }} since last run</v-card-text>
            </v-card>
          </v-col>
        </v-row>

        <v-card>
          <v-card-title class="text-title-small">Scraped Job Listing</v-card-title>
          <v-list>
            <v-list-item-group>
              <v-list-item v-for="(item, index) in items" :key="index">
                <v-list-item-content>
                  <v-list-item-title>{{ item.title }}</v-list-item-title>
                  <v-list-item-subtitle>{{ item.subtitle }}</v-list-item-subtitle>
                </v-list-item-content>
              </v-list-item>
            </v-list-item-group>
          </v-list>
        </v-card>
      </v-container>
    </v-main>
  </v-app>
</template>

<script lang="ts" setup>
import { ref } from 'vue';

const items = ref([{ title: 'Item 1', subtitle: 'test subtitle'}]);
const totalJobsScraped = ref(100);
const totalJobsScrapedComparison = ref('+8.5%')
</script>
