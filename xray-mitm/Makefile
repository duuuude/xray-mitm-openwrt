include $(TOPDIR)/rules.mk

PKG_NAME:=xray-mitm
PKG_VERSION:=0.2.1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=duuuude

include $(INCLUDE_DIR)/package.mk

define Package/xray-mitm
  PKGARCH:=all
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=Standalone Xray MITM Domain Fronting service
  URL:=https://github.com/duuuude/xray-mitm-openwrt
  DEPENDS:=@USE_APK +xray-core +curl +openssl-util +uci +jsonfilter +coreutils-stat +v2ray-geoip +v2ray-geosite
endef

define Package/xray-mitm/description
 Architecture-independent service, certificate lifecycle, health check, and
 optional PassWall2 integration for a standalone Xray MITM-DomainFronting path.
 Installation does not generate a CA, start the service, or alter routing.
endef

define Package/xray-mitm/conffiles
/etc/config/xray-mitm
/etc/xray-mitm/
endef

define Build/Compile
endef

define Package/xray-mitm/install
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_CONF) ./files/etc/config/xray-mitm $(1)/etc/config/xray-mitm
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/xray-mitm $(1)/etc/init.d/xray-mitm
	$(INSTALL_DIR) $(1)/usr/libexec/xray-mitm
	$(INSTALL_BIN) ./files/usr/libexec/xray-mitm/cert $(1)/usr/libexec/xray-mitm/cert
	$(INSTALL_BIN) ./files/usr/libexec/xray-mitm/check $(1)/usr/libexec/xray-mitm/check
	$(INSTALL_BIN) ./files/usr/libexec/xray-mitm/config $(1)/usr/libexec/xray-mitm/config
	$(INSTALL_BIN) ./files/usr/libexec/xray-mitm/passwall2 $(1)/usr/libexec/xray-mitm/passwall2
	$(INSTALL_DATA) ./files/usr/libexec/xray-mitm/common.sh $(1)/usr/libexec/xray-mitm/common.sh
	$(INSTALL_BIN) ./files/usr/libexec/xray-mitm-check $(1)/usr/libexec/xray-mitm-check
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/usr/sbin/xray-mitmctl $(1)/usr/sbin/xray-mitmctl
	$(INSTALL_DIR) $(1)/usr/share/xray-mitm
	$(INSTALL_DATA) ./files/usr/share/xray-mitm/config.json.example $(1)/usr/share/xray-mitm/config.json.example
endef

$(eval $(call BuildPackage,xray-mitm))
