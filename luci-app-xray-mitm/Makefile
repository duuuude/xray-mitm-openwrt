include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI support for Xray MITM Domain Fronting
LUCI_DEPENDS:=@USE_APK +luci-base +xray-mitm +rpcd-mod-ucode +ucode-mod-fs
LUCI_PKGARCH:=all

PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=duuuude

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
