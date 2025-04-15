/* Get Start Example

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/


/**
 * In this file, the following code blocks are marked for customization.
 * Each block starts with the comment: "// YOUR CODE HERE" 
 * and ends with: "// END OF YOUR CODE".
 *
 * [1] Modify the CSI Buffer and FIFO Lengths:
 *     - Adjust the buffer configuration based on your system if necessary.
 *
 * [2] Implement Algorithms:
 *     - Develop algorithms for motion detection, breathing rate estimation, and MQTT message sending.
 *     - Implement them in their respective functions.
 *
 * [3] Modify Wi-Fi Configuration:
 *     - Modify the Wi-Fi settings–SSID and password to connect to your router.
 *
 * [4] Finish the function `csi_process()`:
 *     - Fill in the group information.
 *     - Process and analyze CSI data in the `csi_process` function.
 *     - Implement your algorithms in this function if on-board. (Task 2)
 *     - Return the results to the host or send the CSI data via MQTT. (Task 3)
 *
 * Feel free to modify these sections to suit your project requirements!
 * 
 * Have fun building!
 */


#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "nvs_flash.h"
#include "esp_mac.h"
#include "rom/ets_sys.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_now.h"


#include "mqtt_client.h"

#define WIFI_SSID "HyperOS2"
#define WIFI_PASS "1685087768"

// [1] YOUR CODE HERE
#define CSI_BUFFER_LENGTH 800
#define CSI_FIFO_LENGTH 100
static int16_t CSI_Q[CSI_BUFFER_LENGTH];
static int CSI_Q_INDEX = 0; // CSI Buffer Index
// Enable/Disable CSI Buffering. 1: Enable, using buffer, 0: Disable, using serial output
static bool CSI_Q_ENABLE = 1; 
static void csi_process(const int8_t *csi_data, int length);
// [1] END OF YOUR CODE


// [2] YOUR CODE HERE
// Modify the following functions to implement your algorithms.
// NOTE: Please do not change the function names and return types.
bool motion_detection() {
    // TODO: Implement motion detection logic using CSI data in CSI_Q
    return false; // Placeholder
}

int breathing_rate_estimation() {
    // TODO: Implement breathing rate estimation using CSI data in CSI_Q
    return 18; // Placeholder
}


static esp_mqtt_client_handle_t mqtt_client = NULL;
static bool mqtt_connected = false;

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;
    esp_mqtt_client_handle_t client = event->client;
    const char *TAG = "mqtt";

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT_EVENT_CONNECTED");
            mqtt_connected = true;
            break;
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT_EVENT_DISCONNECTED");
            break;
        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT_EVENT_ERROR");
            break;
        default:
            ESP_LOGI(TAG, "Other event id:%d", event->event_id);
            break;
    }
}

void mqtt_app_start(void)
{
    const esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = "mqtt://192.168.77.93",  // 你的 MQTT Broker 地址
    };

    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (mqtt_client == NULL) {
        ESP_LOGE("mqtt", "Failed to create MQTT client");
        return;
    }

    // 注册事件回调（新版本方式）
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);

    esp_mqtt_client_start(mqtt_client);
    ESP_LOGI("mqtt", "MQTT client started.");
}

void mqtt_send()
{
    if (mqtt_client == NULL) {
        mqtt_app_start();
        ESP_LOGW("mqtt", "MQTT client is not initialized yet.");
        return;
    }

    // 等待首次连接成功
    if (!mqtt_connected) {
        ESP_LOGW("mqtt", "MQTT not connected yet.");
        return;
    }

    int bpm = breathing_rate_estimation();
    char msg[64];
    snprintf(msg, sizeof(msg), "{\"breathing_bpm\": %d}", bpm);

    int msg_id = esp_mqtt_client_publish(mqtt_client, "/esp32/breathing", msg, 0, 1, 0);
    ESP_LOGI("mqtt", "MQTT message sent: id=%d | payload=%s", msg_id, msg);
}



// [2] END OF YOUR CODE


#define CONFIG_LESS_INTERFERENCE_CHANNEL    11
#define CONFIG_WIFI_BAND_MODE               WIFI_BAND_MODE_2G_ONLY
#define CONFIG_WIFI_2G_BANDWIDTHS           WIFI_BW_HT20
#define CONFIG_WIFI_5G_BANDWIDTHS           WIFI_BW_HT20
#define CONFIG_WIFI_2G_PROTOCOL             WIFI_PROTOCOL_11N
#define CONFIG_WIFI_5G_PROTOCOL             WIFI_PROTOCOL_11N
#define CONFIG_ESP_NOW_PHYMODE              WIFI_PHY_MODE_HT20
#define CONFIG_ESP_NOW_RATE                 WIFI_PHY_RATE_MCS0_LGI
#define CONFIG_FORCE_GAIN                   1
#define CONFIG_GAIN_CONTROL                 CONFIG_FORCE_GAIN

// UPDATE: Define parameters for scan method
#if CONFIG_EXAMPLE_WIFI_ALL_CHANNEL_SCAN
#define DEFAULT_SCAN_METHOD WIFI_ALL_CHANNEL_SCAN
#elif CONFIG_EXAMPLE_WIFI_FAST_SCAN
#define DEFAULT_SCAN_METHOD WIFI_FAST_SCAN
#else
#define DEFAULT_SCAN_METHOD WIFI_FAST_SCAN
#endif /*CONFIG_EXAMPLE_SCAN_METHOD*/
//

static const uint8_t CONFIG_CSI_SEND_MAC[] = {0x1A, 0x2B, 0x3C, 0x4D, 0x5E, 0x6F};
static const char *TAG = "csi_recv";
typedef struct
{
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 16; /**< reserved */
    unsigned fft_gain : 8;
    unsigned agc_gain : 8;
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
    unsigned : 32; /**< reserved */
} wifi_pkt_rx_ctrl_phy_t;

#if CONFIG_FORCE_GAIN
    /**
     * @brief Enable/disable automatic fft gain control and set its value
     * @param[in] force_en true to disable automatic fft gain control
     * @param[in] force_value forced fft gain value
     */
    extern void phy_fft_scale_force(bool force_en, uint8_t force_value);

    /**
     * @brief Enable/disable automatic gain control and set its value
     * @param[in] force_en true to disable automatic gain control
     * @param[in] force_value forced gain value
     */
    extern void phy_force_rx_gain(int force_en, int force_value);
#endif

static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                             int32_t event_id, void* event_data);
static bool wifi_connected = false;

//------------------------------------------------------WiFi Initialize------------------------------------------------------
static void wifi_init()
{
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(esp_netif_init());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                      ESP_EVENT_ANY_ID,
                                                      &wifi_event_handler,
                                                      NULL,
                                                      &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                      IP_EVENT_STA_GOT_IP,
                                                      &wifi_event_handler,
                                                      NULL,
                                                      &instance_got_ip));
    
    // [3] YOUR CODE HERE
    // You need to modify the ssid and password to match your Wi-Fi network.
    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,         
            .password = WIFI_PASS,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            // UPDATES: only use this scan method when you want to connect your mobile phone's hotpot
            .scan_method = DEFAULT_SCAN_METHOD,
            //
        
            .pmf_cfg = {
                .capable = true,
                .required = false
            },
        },
    };
    // [3] END OF YOUR CODE

    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "wifi_init finished.");
}

//------------------------------------------------------WiFi Event Handler------------------------------------------------------
static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                             int32_t event_id, void* event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Trying to connect to AP...");
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGI(TAG, "Connection failed! Retrying...");
        wifi_connected = false;
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "Got IP:" IPSTR, IP2STR(&event->ip_info.ip));
        wifi_connected = true;
        
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            ESP_LOGI(TAG, "Connected to AP - SSID: %s, Channel: %d, RSSI: %d",
                    ap_info.ssid, ap_info.primary, ap_info.rssi);
        }
    }
}

//------------------------------------------------------ESP-NOW Initialize------------------------------------------------------
static void wifi_esp_now_init(esp_now_peer_info_t peer) 
{
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((uint8_t *)"pmk1234567890123"));
    esp_now_rate_config_t rate_config = {
        .phymode = CONFIG_ESP_NOW_PHYMODE, 
        .rate = CONFIG_ESP_NOW_RATE,//  WIFI_PHY_RATE_MCS0_LGI,    
        .ersu = false,                     
        .dcm = false                       
    };
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(peer.peer_addr,&rate_config));
    ESP_LOGI(TAG, "================ ESP NOW Ready ================");
    ESP_LOGI(TAG, "esp_now_init finished.");
}

//------------------------------------------------------CSI Callback------------------------------------------------------
static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf) return;

    ESP_LOGI(TAG, "CSI callback triggered");

    // Applying the CSI_Q_ENABLE flag to determine the output method
    // 1: Enable, using buffer, 0: Disable, using serial output
    if (!CSI_Q_ENABLE) {
        ets_printf("CSI_DATA,%d," MACSTR ",%d,%d,%d,%d\n",
                   info->len, MAC2STR(info->mac), info->rx_ctrl.rssi,
                   info->rx_ctrl.rate, info->rx_ctrl.noise_floor,
                   info->rx_ctrl.channel);
    } else {
        csi_process(info->buf, info->len);
    }

    
    if (!info || !info->buf) {
        ESP_LOGW(TAG, "<%s> wifi_csi_cb", esp_err_to_name(ESP_ERR_INVALID_ARG));
        return;
    }

    ESP_LOGI(TAG, "Received MAC: "MACSTR", Expected MAC: "MACSTR, 
             MAC2STR(info->mac), MAC2STR(CONFIG_CSI_SEND_MAC));
    
    if (memcmp(info->mac, CONFIG_CSI_SEND_MAC, 6)) {
        ESP_LOGI(TAG, "MAC address doesn't match, skipping packet");
        return;
    }

    wifi_pkt_rx_ctrl_phy_t *phy_info = (wifi_pkt_rx_ctrl_phy_t *)info;
    static int s_count = 0;

#if CONFIG_GAIN_CONTROL
    static uint16_t agc_gain_sum=0; 
    static uint16_t fft_gain_sum=0; 
    static uint8_t agc_gain_force_value=0; 
    static uint8_t fft_gain_force_value=0; 
    if (s_count<100) {
        agc_gain_sum += phy_info->agc_gain;
        fft_gain_sum += phy_info->fft_gain;
    }else if (s_count == 100) {
        agc_gain_force_value = agc_gain_sum/100;
        fft_gain_force_value = fft_gain_sum/100;
    #if CONFIG_FORCE_GAIN
        phy_fft_scale_force(1,fft_gain_force_value);
        phy_force_rx_gain(1,agc_gain_force_value);
    #endif
        ESP_LOGI(TAG,"fft_force %d, agc_force %d",fft_gain_force_value,agc_gain_force_value);
    }
#endif

    const wifi_pkt_rx_ctrl_t *rx_ctrl = &info->rx_ctrl;
    if (CSI_Q_ENABLE == 0) {
        ESP_LOGI(TAG, "================ CSI RECV via Serial Port ================");
        ets_printf("CSI_DATA,%d," MACSTR ",%d,%d,%d,%d,%d,%d,%d,%d,%d",
            s_count++, MAC2STR(info->mac), rx_ctrl->rssi, rx_ctrl->rate,
            rx_ctrl->noise_floor, phy_info->fft_gain, phy_info->agc_gain, rx_ctrl->channel,
            rx_ctrl->timestamp, rx_ctrl->sig_len, rx_ctrl->rx_state);
        ets_printf(",%d,%d,\"[%d", info->len, info->first_word_invalid, info->buf[0]);

        for (int i = 1; i < info->len; i++) {
            ets_printf(",%d", info->buf[i]);
        }
        ets_printf("]\"\n");
    }

    else{
        ESP_LOGI(TAG, "================ CSI RECV via Buffer ================");
        csi_process(info->buf, info->len);
    }
}

//------------------------------------------------------CSI Processing & Algorithms------------------------------------------------------
static void csi_process(const int8_t *csi_data, int length)
{   
    if (CSI_Q_INDEX + length > CSI_BUFFER_LENGTH) {
        int shift_size = CSI_BUFFER_LENGTH - CSI_FIFO_LENGTH;
        memmove(CSI_Q, CSI_Q + CSI_FIFO_LENGTH, shift_size * sizeof(int16_t));
        CSI_Q_INDEX = shift_size;
    }    
    ESP_LOGI(TAG, "CSI Buffer Status: %d samples stored", CSI_Q_INDEX);
    // Append new CSI data to the buffer
    for (int i = 0; i < length && CSI_Q_INDEX < CSI_BUFFER_LENGTH; i++) {
        CSI_Q[CSI_Q_INDEX++] = (int16_t)csi_data[i];
    }

    // [4] YOUR CODE HERE

    // 1. Fill the information of your group members
    ESP_LOGI(TAG, "================ GROUP INFO ================");
    const char *TEAM_MEMBER[] = {"a", "b", "c", "d"};
    const char *TEAM_UID[] = {"1", "2", "3", "4"};
    ESP_LOGI(TAG, "TEAM_MEMBER: %s, %s, %s, %s | TEAM_UID: %s, %s, %s, %s",
                TEAM_MEMBER[0], TEAM_MEMBER[1], TEAM_MEMBER[2], TEAM_MEMBER[3],
                TEAM_UID[0], TEAM_UID[1], TEAM_UID[2], TEAM_UID[3]);
    ESP_LOGI(TAG, "================ END OF GROUP INFO ================");

    // 2. Call your algorithm functions here, e.g.: motion_detection(), breathing_rate_estimation(), and mqtt_send()
    // If you implement the algorithm on-board, you can return the results to the host, else send the CSI data.
    // motion_detection();
    // breathing_rate_estimation();
    mqtt_send();
    // [4] END YOUR CODE HERE
}


//------------------------------------------------------CSI Config Initialize------------------------------------------------------
static void wifi_csi_init()
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    wifi_csi_config_t csi_config = {
        .enable                   = true,                           
        .acquire_csi_legacy       = false,               
        .acquire_csi_force_lltf   = false,           
        .acquire_csi_ht20         = true,                  
        .acquire_csi_ht40         = true,                  
        .acquire_csi_vht          = false,                  
        .acquire_csi_su           = false,                   
        .acquire_csi_mu           = false,                   
        .acquire_csi_dcm          = false,                  
        .acquire_csi_beamformed   = false,           
        .acquire_csi_he_stbc_mode = 2,                                                                                                                                                                                                                                                                               
        .val_scale_cfg            = 0,                    
        .dump_ack_en              = false,                      
        .reserved                 = false                         
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

//------------------------------------------------------Main Function------------------------------------------------------
void app_main()
{
    /**
     * @brief Initialize NVS
     */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /**
     * @brief Initialize Wi-Fi
     */
    wifi_init();

    // Get Device MAC Address
    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    ESP_LOGI(TAG, "Device MAC Address: " MACSTR, MAC2STR(mac));

    // Try to connect to WiFi
    ESP_LOGI(TAG, "Connecting to WiFi...");

    // Wait for Wi-Fi connection
    int retry_count = 0;
    bool wifi_connected = false;
    while (!wifi_connected && retry_count < 20) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        retry_count++;
        ESP_LOGI(TAG, "Waiting for Wi-Fi connection... (%d/20)", retry_count);

        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            ESP_LOGI(TAG, "Connected to SSID: %s, RSSI: %d, Channel: %d", ap_info.ssid, ap_info.rssi, ap_info.primary);
            wifi_connected = true;
        }
    }

    /**
     * @brief Initialize ESP-NOW
     */
    // wifi_connected = 1;
    
    if (wifi_connected) {
        esp_now_peer_info_t peer = {
            .channel   = CONFIG_LESS_INTERFERENCE_CHANNEL,
            .ifidx     = WIFI_IF_STA,
            .encrypt   = false,
            .peer_addr = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff},
        };
        
        wifi_esp_now_init(peer); // Initialize ESP-NOW Communication
        ESP_LOGI(TAG, "wifi_esp_now_init");
        wifi_csi_init(); // Initialize CSI Collection
        ESP_LOGI(TAG, "wifi_csi_init");

    } else {
        ESP_LOGI(TAG, "WiFi connection failed");
        return;
    }
}
