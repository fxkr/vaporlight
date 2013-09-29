name := "de.entropia.vapor.daemon"

version := "0.1.0-SNAPSHOT"

scalaVersion := "2.10.2"

resolvers ++= Seq(
    "Typesafe Repository" at "http://repo.typesafe.com/typesafe/releases/",
    "sonatype-public" at "https://oss.sonatype.org/content/groups/public",
    "sparetimelabs" at "http://www.sparetimelabs.com/maven2"
)

libraryDependencies ++= Seq(
    "org.scalatest" %% "scalatest" % "1.9.1" % "test",
    "junit" % "junit" % "4.8.1" % "test",
    "io.netty" % "netty" % "3.5.10.Final",
    "ch.qos.logback" % "logback-classic" % "1.0.3",
    "com.typesafe" %% "scalalogging-slf4j" % "1.0.1",
    "com.sparetimelabs" % "purejavacomm" % "0.0.16" classifier "",
    "com.typesafe" % "config" % "1.0.0",
    "net.databinder" %% "unfiltered-filter" % "0.7.0",
    "net.databinder" %% "unfiltered-netty-server" % "0.7.0"
)

seq(com.github.retronym.SbtOneJar.oneJarSettings: _*)

mainClass in oneJar := Some("de.entropia.vapor.daemon.Application")

seq(ScctPlugin.instrumentSettings : _*)

